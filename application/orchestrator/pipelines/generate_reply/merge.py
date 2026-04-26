"""Phase 3 — merge_reply.py + optional Phase 3b post-merge actualization.

merge_reply.py is a pure Python script (no agent). It reads reply_plan.json
and reply_turn_*.json, writes pending_turns.json (the canonical post-round
artifact) at output_path, and deletes the intermediates.

If CLAUDE.overwrite.md defines Phase 3b, the actualizer agent runs after
merge using pending_turns.json + turn_state.json (prior round) as inputs.
The agent's exact behavior is overwrite-defined and not specified here.
"""

from __future__ import annotations

import subprocess
import sys

from ...env import TavernConfig
from ...prompts import REPO, build_prompt, build_required_reads
from ...sdk import spawn_agent


_PHASE_3B_BASE = [
    "CLAUDE.overwrite.md",
    "infrastructure/dialogues/{dialogue_id}/pending_turns.json",
]
_PHASE_3B_OPTIONAL = [
    "infrastructure/dialogues/{dialogue_id}/turn_state.json",
    "infrastructure/dialogues/{dialogue_id}/actualized_climax_history.json",
]


async def run_phase_3(dialogue_id: str, output_path: str, cfg: TavernConfig) -> None:
    # Phase 3 — deterministic merge
    subprocess.run(
        [sys.executable, "application/scripts/merge_reply.py",
         "--dialogue-id", dialogue_id,
         "--output-path", output_path],
        cwd=str(REPO),
        check=True,
    )

    # Phase 3b — post-merge actualizer (if overwrite defines it)
    if cfg.has_phase_3b:
        await _run_phase_3b(dialogue_id, output_path, cfg)


async def _run_phase_3b(dialogue_id: str, output_path: str, cfg: TavernConfig) -> None:
    required, absent = build_required_reads(
        base=_PHASE_3B_BASE,
        optional=_PHASE_3B_OPTIONAL,
        dialogue_id=dialogue_id,
    )

    extra = [
        f"Dialogue ID: {dialogue_id}",
        "",
        "You are the Phase 3b post-merge actualization agent (defined in CLAUDE.overwrite.md).",
        "Read pending_turns.json (the post-merge artifact) and turn_state.json (prior round) "
        "if it exists. Write actualized_turn_state.json (always) and "
        "actualized_climax_history.json (only when the round contains a climax-weight turn).",
        "",
        "Schema and rules are defined in CLAUDE.overwrite.md — that file's contents are the "
        "authoritative spec for this phase.",
    ]
    prompt = build_prompt(
        instruction_file="(see CLAUDE.overwrite.md Phase 3b)",
        task_json={"dialogue_id": dialogue_id, "phase": "3b", "purpose": "post-merge state actualization"},
        required_reads=required,
        absent_confirmed=absent,
        extra_lines=extra,
    )
    result = await spawn_agent(
        prompt, model="haiku", allowed_tools=["Read", "Write"],
        label="phase3b actualizer",
        thinking_budget="off",
        dialogue_id=dialogue_id,
    )
    if result.is_error:
        raise RuntimeError(f"Phase 3b actualizer error: {result.text[:500]}")
