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
from typing import Any

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


async def run(item: dict[str, Any], cfg: TavernConfig) -> None:
    dialogue_id: str = item["input"]["dialogue_id"]
    user_prompt: str | None = item["input"].get("user_prompt")
    output_path: str = item["output_path"]

    # Pre-flight: clear stale per-round artifacts from any prior failed run.
    deleted = _clear_stale_round_artifacts(dialogue_id)
    if deleted:
        print(f"  [cleanup] cleared stale: {', '.join(deleted)}", flush=True)
    else:
        print("  [cleanup] no stale artifacts", flush=True)

    # Phase 0 — five prep scripts
    prep.run_phase_0(dialogue_id, user_prompt)

    # Phase 0b — narrator → normal mode transition bridge (only if state demands it)
    await transition.maybe_run(dialogue_id, cfg)

    # Phase 1 — plan, with Phase 1b validate + 1c handler loop
    await _plan_validate_handle_loop(dialogue_id, item, cfg)

    # Phase 2 — generate turns
    await turns.run_phase_2(dialogue_id, item, cfg)

    # Phase 3 — merge + optional Phase 3b actualization
    await merge.run_phase_3(dialogue_id, output_path, cfg)

    # Phase 4 — append + optional 4b finalization + condense check
    await append.run_phase_4(dialogue_id, output_path, user_prompt, cfg)


# Check IDs that ALWAYS demand a full replan — no patch can recover. Detected
# directly by the orchestrator from plan_validation.json so we don't waste a
# Sonnet handler spawn just to delete reply_plan.json + write status:"restart".
# These mirror the categorical-critical list in handle_plan_validation.md.
_UNCONDITIONAL_CRITICAL_CHECKS = {
    "2b1c_missing_reactor",            # planner omitted a Tier 1 reactor
    "2b_turn_order",                   # last char speaker in turn_order doesn't match reply_history
    "2g_narrator_speech_purity",       # asterisk action in a narrator-mode speech turn
    "2g_narrator_speech_action_mixed", # action interleaved with dialogue
    "2h_scene_anchor_contradiction",   # plan reverses time / teleports / silently changes wardrobe vs prior round
}

# Check IDs whose criticality depends on scope (e.g. 2f2 majority threshold).
# We compute the scope inside _detect_critical and decide there.
_SCOPED_CRITICAL_CHECKS = {"2f2"}


def _detect_critical(verdict: dict[str, Any], dialogue_id: str) -> tuple[bool, str]:
    """Decide if validation failure is critical without spawning the handler.

    Returns (is_critical, reason). On True, the orchestrator deletes the plan
    and replans immediately. On False, the handler agent decides per-issue.
    """
    issues = verdict.get("issues") or []
    errors = [i for i in issues if i.get("severity") == "error"]
    if not errors:
        return False, ""

    # Pattern 1: any unconditionally-critical check ID.
    for issue in errors:
        check = issue.get("check") or ""
        if check in _UNCONDITIONAL_CRITICAL_CHECKS:
            spk = issue.get("speaker") or "?"
            return True, f"{check} on {spk} — unconditionally critical"

    # Pattern 2: 2f2 (cross-character ability leakage) on >50% of turns.
    f2_speakers = {i.get("speaker") for i in errors if i.get("check") == "2f2"}
    if f2_speakers:
        plan_path = REPO / "infrastructure" / "dialogues" / dialogue_id / "reply_plan.json"
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            total = len(plan_data.get("turns") or [])
            affected = sum(
                1 for t in plan_data.get("turns") or []
                if t.get("speaker") in f2_speakers
            )
            if total > 0 and affected * 2 > total:
                return True, f"2f2 leakage on {affected}/{total} turns (majority)"
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    return False, ""


def _orchestrator_critical_restart(dialogue_id: str, reason: str) -> None:
    """Delete plan + validation + write a synthetic handler_result for traceability."""
    dlg_dir = REPO / "infrastructure" / "dialogues" / dialogue_id
    for name in ("reply_plan.json", "plan_validation.json"):
        p = dlg_dir / name
        if p.exists():
            p.unlink()
    # Synthetic handler_result.json — mimics what the handler would have written
    # so any downstream tooling that inspects it sees a consistent record.
    result = {
        "status": "restart",
        "reason": reason,
        "decided_by": "orchestrator (short-circuit, no handler spawn)",
    }
    (dlg_dir / "handler_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def _plan_validate_handle_loop(dialogue_id: str, item: dict[str, Any], cfg: TavernConfig) -> None:
    """Plan → validate → on fail short-circuit critical / spawn handler for fixable.

    Capped at 3 plan attempts and 3 handler patches per plan to avoid loops.
    """
    plan_attempts = 0
    while True:
        plan_attempts += 1
        if plan_attempts > 3:
            raise RuntimeError(f"Plan phase exceeded 3 attempts for dialogue {dialogue_id}")

        await plan.run_phase_1(dialogue_id, item, cfg)

        patches = 0
        while True:
            await validate.run_phase_1b(dialogue_id, item, cfg)
            verdict = _read_validation(dialogue_id)
            if verdict.get("status") == "pass":
                print("  [orchestrator] validation passed -> Phase 2", flush=True)
                return  # done — proceed to Phase 2

            # Short-circuit critical-failure path: orchestrator detects it
            # straight from plan_validation.json and replans without spawning
            # the Sonnet handler agent.
            is_critical, reason = _detect_critical(verdict, dialogue_id)
            if is_critical:
                print(f"  [phase1c orchestrator] CRITICAL — {reason} → replan", flush=True)
                _orchestrator_critical_restart(dialogue_id, reason)
                break  # outer loop — replan from scratch

            patches += 1
            if patches > 3:
                raise RuntimeError(f"Handler exceeded 3 patches for dialogue {dialogue_id}")

            handler_result = await handler.run_phase_1c(dialogue_id, item, cfg, verdict)
            status = handler_result.get("status")
            if status == "restart":
                break  # back to outer loop — replan
            if status == "patched":
                if not handler_result.get("revalidation_needed"):
                    return  # trim-only patch + sizing verified — skip to Phase 2
                continue  # re-validate the patched plan
            raise RuntimeError(f"Unknown handler status {status!r} for dialogue {dialogue_id}")


def _read_validation(dialogue_id: str) -> dict[str, Any]:
    p = REPO / "infrastructure" / "dialogues" / dialogue_id / "plan_validation.json"
    return json.loads(p.read_text(encoding="utf-8"))
