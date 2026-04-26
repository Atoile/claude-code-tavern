"""Phase 1b — validate plan.

Haiku agent. Reads reply_plan.json + a small set of cross-reference files,
runs check_beat_sizing.py, writes plan_validation.json.

Tier 1 (Step 1): manifest applied — narrator pipeline runs through here too,
so the validate spawn gets Tier 1 unconditionally regardless of chat mode.
"""

from __future__ import annotations

from typing import Any

from ...env import TavernConfig
from ...prompts import build_prompt, build_required_reads
from ...sdk import spawn_agent


_BASE = [
    "infrastructure/dialogues/{dialogue_id}/reply_plan.json",
    "infrastructure/dialogues/{dialogue_id}/character_briefs.json",
    "infrastructure/dialogues/{dialogue_id}/active_lorebook.json",
    "infrastructure/dialogues/{dialogue_id}/characters.json",
    "domain/dialogue/writing_rules_cache.md",
]
_OPTIONAL = [
    "infrastructure/dialogues/{dialogue_id}/reply_history.json",
    "infrastructure/dialogues/{dialogue_id}/tbc.json",
    "infrastructure/dialogues/{dialogue_id}/last_turn.json",
    "infrastructure/dialogues/{dialogue_id}/scene_state.json",
    "application/dialogue/validate_plan.overwrite.md",
]


async def run_phase_1b(dialogue_id: str, item: dict[str, Any], cfg: TavernConfig) -> None:
    required, absent = build_required_reads(
        base=_BASE,
        optional=_OPTIONAL,
        dialogue_id=dialogue_id,
    )

    # Strip output_path so the agent can't shortcut to writing pending_turns.json
    # — the validator's job is plan_validation.json only.
    sanitized_item = {k: v for k, v in item.items() if k != "output_path"}

    extra = [
        f"Dialogue ID: {dialogue_id}",
        "",
        "OUTPUT CONTRACT:",
        f"- Write ONLY infrastructure/dialogues/{dialogue_id}/plan_validation.json.",
        "- DO NOT write pending_turns.json, reply_plan.json, or any other file.",
    ]
    prompt = build_prompt(
        instruction_file="application/dialogue/validate_plan.md",
        task_json=sanitized_item,
        required_reads=required,
        absent_confirmed=absent,
        extra_lines=extra,
    )
    # Validator runs check_beat_sizing.py via Bash — needs that tool.
    result = await spawn_agent(
        prompt,
        model="haiku",
        allowed_tools=["Read", "Write", "Bash"],
        label="phase1b validate",
        thinking_budget="off",
        dialogue_id=dialogue_id,
    )
    if result.is_error:
        raise RuntimeError(f"validator agent error: {result.text[:500]}")
