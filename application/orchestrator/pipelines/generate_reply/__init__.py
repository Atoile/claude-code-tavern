"""generate_reply pipeline — orchestrates Phase 0 → 4 for one queue item.

Step 1 scope:
- Narrator-mode end-to-end with Tier 1 manifests on every spawn.
- Normal-mode end-to-end works but Tier 1 is deferred to Step 2 (static
  prompts on the normal-mode planner and turn agents).
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, cast

from ...env import TavernConfig
from ...prompts import REPO

from . import prep, transition, plan, validate, handler, turns, merge, append


# Per-round artifacts that should not survive between rounds. cleanup_round.py
# handles successful runs; this list handles cleanup at the START of a new
# round so that a previous failed run can't pollute fresh state.
_STALE_ARTIFACTS = [
    "reply_plan.json",
    "plan_validation.json",
    "handler_result.json",
    "beat_sizing.json",
    "plan_turn_order.json",
    "pending_turns.json",
]
_STALE_GLOBS = [
    "plan_slice_*.json",
    "reply_turn_*.json",
    "turn_context_*.json",
]


def _clear_stale_round_artifacts(dialogue_id: str) -> list[str]:
    """Delete leftover per-round files. Returns the list of deleted paths."""
    dlg_dir = REPO / "infrastructure" / "dialogues" / dialogue_id
    if not dlg_dir.exists():
        return []
    deleted: list[str] = []
    for name in _STALE_ARTIFACTS:
        p = dlg_dir / name
        if p.exists():
            p.unlink()
            deleted.append(name)
    for pattern in _STALE_GLOBS:
        for path_str in glob.glob(str(dlg_dir / pattern)):
            os.unlink(path_str)
            deleted.append(os.path.basename(path_str))
    return deleted


_PHASES = ["phase0", "phase0b", "phase1", "phase1b", "phase2", "phase3", "phase4"]


async def run(item: dict[str, Any], cfg: TavernConfig, start_from: str | None = None) -> None:
    dialogue_id: str = item["input"]["dialogue_id"]
    user_prompt: str | None = item["input"].get("user_prompt")
    output_path: str = item["output_path"]

    if start_from is not None and start_from not in _PHASES:
        raise ValueError(f"Unknown phase {start_from!r}. Valid: {_PHASES}")
    start_idx = _PHASES.index(start_from) if start_from else 0

    def _skip(phase: str) -> bool:
        return _PHASES.index(phase) < start_idx

    # Pre-flight: clear stale artifacts only on a full run. When resuming
    # mid-pipeline the existing files are the point — don't wipe them.
    if not _skip("phase0"):
        deleted = _clear_stale_round_artifacts(dialogue_id)
        if deleted:
            print(f"  [cleanup] cleared stale: {', '.join(deleted)}", flush=True)
        else:
            print("  [cleanup] no stale artifacts", flush=True)
    else:
        print(f"  [resume] starting from {start_from}", flush=True)

    # Phase 0 — five prep scripts
    if not _skip("phase0"):
        prep.run_phase_0(dialogue_id, user_prompt)

    # Phase 0b — narrator → normal mode transition bridge (only if state demands it)
    if not _skip("phase0b"):
        await transition.maybe_run(dialogue_id, cfg)

    # Phase 1 — plan + Phase 1b validate + 1c handler
    if not _skip("phase1b"):
        await _plan_validate_handle_loop(dialogue_id, item, cfg, skip_plan=_skip("phase1"))

    # Phase 2 — generate turns
    if not _skip("phase2"):
        await turns.run_phase_2(dialogue_id, item, cfg)

    # Phase 3 — merge + optional Phase 3b actualization
    if not _skip("phase3"):
        await merge.run_phase_3(dialogue_id, output_path, cfg)

    # Phase 4 — append + optional 4b finalization + condense check
    if not _skip("phase4"):
        await append.run_phase_4(dialogue_id, output_path, user_prompt, cfg)


class ValidationError(RuntimeError):
    """Raised on a critical validation failure.

    reply_plan.json and plan_validation.json are left on disk for debugging.
    The next run's pre-flight (_clear_stale_round_artifacts) will sweep them.
    """


# Check IDs that are always critical — no handler spawn needed.
# Mirrors the categorical-critical list in handle_plan_validation.md.
_UNCONDITIONAL_CRITICAL_CHECKS = {
    "2b1c_missing_reactor",
    "2b_turn_order",
    "2g_narrator_speech_purity",
    "2g_narrator_speech_action_mixed",
    "2h_scene_anchor_contradiction",
}


def _detect_critical(verdict: dict[str, Any], dialogue_id: str) -> tuple[bool, str]:
    """Return (is_critical, reason) from plan_validation.json without spawning the handler."""
    issues_raw: Any = verdict.get("issues") or []
    issues: list[dict[str, Any]] = [
        cast(dict[str, Any], it)
        for it in (cast(list[Any], issues_raw) if isinstance(issues_raw, list) else [])
        if isinstance(it, dict)
    ]
    errors = [i for i in issues if i.get("severity") == "error"]
    if not errors:
        return False, ""

    for issue in errors:
        check: str = issue.get("check") or ""
        if check in _UNCONDITIONAL_CRITICAL_CHECKS:
            speaker: str = issue.get("speaker") or "?"
            return True, f"{check} on {speaker} — unconditionally critical"

    # 2f2: critical only when majority of turns are affected.
    f2_speakers: set[Any] = {i.get("speaker") for i in errors if i.get("check") == "2f2"}
    if f2_speakers:
        plan_path = REPO / "infrastructure" / "dialogues" / dialogue_id / "reply_plan.json"
        try:
            plan_data = cast(dict[str, Any], json.loads(plan_path.read_text(encoding="utf-8")))
            plan_turns = cast(list[Any], plan_data.get("turns") or [])
            total = len(plan_turns)
            affected = sum(
                1 for t in plan_turns
                if isinstance(t, dict) and cast(dict[str, Any], t).get("speaker") in f2_speakers
            )
            if total > 0 and affected * 2 > total:
                return True, f"2f2 leakage on {affected}/{total} turns (majority)"
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    return False, ""


def _report_issues(verdict: dict[str, Any]) -> None:
    issues_raw: Any = verdict.get("issues") or []
    for issue in cast(list[Any], issues_raw) if isinstance(issues_raw, list) else []:
        if isinstance(issue, dict):
            d = cast(dict[str, Any], issue)
            check = d.get("check") or "?"
            severity = d.get("severity") or "?"
            speaker = d.get("speaker") or "?"
            detail = d.get("detail") or ""
            print(f"  [phase1b] {check} | {severity} | {speaker} | {detail}", flush=True)


async def _plan_validate_handle_loop(
    dialogue_id: str, item: dict[str, Any], cfg: TavernConfig, skip_plan: bool = False
) -> None:
    """Plan → validate → error on critical, patch+loop on fixable."""
    if not skip_plan:
        await plan.run_phase_1(dialogue_id, item, cfg)

    patches = 0
    while True:
        await validate.run_phase_1b(dialogue_id, item, cfg)
        verdict = _read_validation(dialogue_id)

        if verdict.get("status") == "pass":
            print("  [orchestrator] validation passed -> Phase 2", flush=True)
            return

        # Critical short-circuit — no handler spawn, raise immediately.
        is_critical, reason = _detect_critical(verdict, dialogue_id)
        if is_critical:
            _report_issues(verdict)
            raise ValidationError(
                f"Plan validation failed ({reason}) for dialogue {dialogue_id} — "
                f"debug files preserved at infrastructure/dialogues/{dialogue_id}/."
            )

        # Fixable — spawn handler.
        patches += 1
        if patches > 3:
            raise RuntimeError(f"Handler exceeded 3 patches for dialogue {dialogue_id}")

        handler_result = await handler.run_phase_1c(dialogue_id, item, cfg, verdict)
        status = handler_result.get("status")

        if status == "restart":
            # Handler classified issues as critical — raise instead of replanning.
            _report_issues(verdict)
            raise ValidationError(
                f"Plan validation failed (handler: {handler_result.get('reason', '?')}) "
                f"for dialogue {dialogue_id} — "
                f"debug files preserved at infrastructure/dialogues/{dialogue_id}/."
            )
        if status == "patched":
            if not handler_result.get("revalidation_needed"):
                return  # trim-only patch + sizing verified — skip to Phase 2
            continue  # re-validate the patched plan
        raise RuntimeError(f"Unknown handler status {status!r} for dialogue {dialogue_id}")


def _read_validation(dialogue_id: str) -> dict[str, Any]:
    p = REPO / "infrastructure" / "dialogues" / dialogue_id / "plan_validation.json"
    return json.loads(p.read_text(encoding="utf-8"))
