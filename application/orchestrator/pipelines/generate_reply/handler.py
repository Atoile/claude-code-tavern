"""Phase 1c — handle plan validation failures.

Sonnet agent classifies issues (critical → restart, fixable → patch in place).
Conditional reads are computed from the failing check IDs in plan_validation.json
— this is the highest-leverage Tier 1 case because the conditional matrix is
six files wide.

Returns the parsed handler_result.json so the orchestrator can decide whether
to restart Phase 1 or re-run Phase 1b.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...env import TavernConfig
from ...prompts import REPO, build_prompt, build_required_reads
from ...sdk import spawn_agent


# Per-check conditional reads. The plan's full breakdown lives in
# handle_plan_validation.md §1 "Read inputs only if these check IDs require them".
# Keep these in sync with that table.
_CHECK_TO_READS: dict[str, list[str]] = {
    "2e": [
        "infrastructure/dialogues/{dialogue_id}/active_lorebook.json",
        "domain/dialogue/writing_rules_cache.md",
    ],
    "2f2": [
        "infrastructure/dialogues/{dialogue_id}/active_lorebook.json",
    ],
    "2b1b": [
        "infrastructure/dialogues/{dialogue_id}/characters.json",
    ],
    "2b1c_missing_reactor": [
        "infrastructure/dialogues/{dialogue_id}/characters.json",
        "infrastructure/dialogues/{dialogue_id}/recent_chat.json",
        "infrastructure/dialogues/{dialogue_id}/reply_history.json",
    ],
    "2b": [
        "infrastructure/dialogues/{dialogue_id}/reply_history.json",
    ],
    "2b4": [
        "infrastructure/dialogues/{dialogue_id}/tbc.json",
    ],
    "2b3_beat_count": [],
    "2b3_beat_oversized": [],
    "2b3_tone_oversized": [],
    "2b3_beat_smuggling": [],
    "2b3_weight_invalid": [],
    "2b3_weight_beat_sizing": [],
    "2b3_narrator_beat_cap": [],
    "2g_narrator_speech_purity": [],
    "2g_narrator_speech_action_mixed": [],
    "2c": [],  # turn ownership — patches are local, no extra reads
    "2d": [],
    "2f": [],
}

# Always-read base for the handler (the failure report + the plan being patched).
_BASE = [
    "infrastructure/dialogues/{dialogue_id}/plan_validation.json",
    "infrastructure/dialogues/{dialogue_id}/reply_plan.json",
]

# Universal optional — every spawn probes its overwrite to avoid wasted Globs.
# character_briefs.json is also always-listed since multiple check categories
# (2f, 2f2, 2f3) reference brief content for cross-character validation.
_UNIVERSAL_OPTIONAL = [
    "infrastructure/dialogues/{dialogue_id}/character_briefs.json",
    "application/dialogue/handle_plan_validation.overwrite.md",
]


def _conditional_reads_for(verdict: dict[str, Any]) -> list[str]:
    failing_checks = {issue.get("check") for issue in verdict.get("issues", [])}
    paths: set[str] = set()
    for check in failing_checks:
        for rel in _CHECK_TO_READS.get(check, []):
            paths.add(rel)
        # Some check IDs match by prefix (e.g. "2b3_*" not in the table fall through).
        for key, rels in _CHECK_TO_READS.items():
            if check and check.startswith(key + "_") and key in {"2b1c"}:
                for rel in rels:
                    paths.add(rel)
    return sorted(paths)


async def run_phase_1c(
    dialogue_id: str, item: dict[str, Any], cfg: TavernConfig, verdict: dict[str, Any]
) -> dict[str, Any]:
    conditional = _conditional_reads_for(verdict) + _UNIVERSAL_OPTIONAL
    required, absent = build_required_reads(
        base=_BASE,
        optional=conditional,
        dialogue_id=dialogue_id,
    )

    # Strip output_path so the handler can't shortcut to pending_turns.json.
    sanitized_item = {k: v for k, v in item.items() if k != "output_path"}

    extra = [
        f"Dialogue ID: {dialogue_id}",
        "",
        "OUTPUT CONTRACT:",
        f"- Write ONLY infrastructure/dialogues/{dialogue_id}/handler_result.json (always),",
        f"  and patch infrastructure/dialogues/{dialogue_id}/reply_plan.json if status=patched.",
        "- DO NOT write pending_turns.json, plan_validation.json, or any other file.",
    ]
    prompt = build_prompt(
        instruction_file="application/dialogue/handle_plan_validation.md",
        task_json=sanitized_item,
        required_reads=required,
        absent_confirmed=absent,
        extra_lines=extra,
    )
    result = await spawn_agent(
        prompt,
        model="sonnet",
        allowed_tools=["Read", "Write", "Edit", "Bash"],
        label="phase1c handler",
        thinking_budget="adaptive",
        dialogue_id=dialogue_id,
    )
    if result.is_error:
        raise RuntimeError(f"handler agent error: {result.text[:500]}")

    handler_result_path = REPO / "infrastructure" / "dialogues" / dialogue_id / "handler_result.json"
    return json.loads(handler_result_path.read_text(encoding="utf-8"))
