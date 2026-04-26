"""Phase 2 — generate turns sequentially.

Mode-routed:
  - normal   → build_turn_context.py + per-turn Sonnet agents (no Tier 1 in Step 1)
  - narrator → split_plan_by_speaker.py + one Haiku expand_round_narrator agent
               (Tier 1 manifest applied)

Step 1 simplification (narrator): we use the single-agent path that writes
ALL turns this round in one spawn (per expand_round_narrator.md's design).
Smart routing (verbatim Route A direct write, per-character Route C reactive)
is a follow-up token optimization, not required for correctness.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ...env import TavernConfig
from ...prompts import REPO, build_prompt, build_required_reads
from ...sdk import spawn_agent


# ─── Narrator mode ──────────────────────────────────────────────────────────

_NARRATOR_BASE = [
    "infrastructure/dialogues/{dialogue_id}/reply_plan.json",
    "infrastructure/dialogues/{dialogue_id}/character_briefs.json",
    "infrastructure/dialogues/{dialogue_id}/prose_tail.json",
    "infrastructure/dialogues/{dialogue_id}/last_turn.json",
    "domain/dialogue/writing_rules_cache.md",
]
_NARRATOR_OPTIONAL = [
    "infrastructure/dialogues/{dialogue_id}/tbc.json",
    "application/dialogue/expand_round_narrator.overwrite.md",
]


async def run_phase_2(dialogue_id: str, item: dict[str, Any], cfg: TavernConfig) -> None:
    if cfg.chat_mode == "narrator":
        await _run_narrator(dialogue_id, item, cfg)
    else:
        await _run_normal(dialogue_id, item, cfg)


async def _run_narrator(dialogue_id: str, item: dict[str, Any], cfg: TavernConfig) -> None:
    # Step A: split the plan into per-speaker slices (used by route C if/when added)
    subprocess.run(
        [sys.executable, "application/scripts/split_plan_by_speaker.py",
         "--dialogue-id", dialogue_id,
         "--narrator-voice", cfg.narrator_voice],
        cwd=str(REPO),
        check=True,
    )

    # Step B: spawn a single expand_round_narrator agent to write all turns this round.
    required, absent = build_required_reads(
        base=_NARRATOR_BASE,
        optional=_NARRATOR_OPTIONAL,
        dialogue_id=dialogue_id,
    )

    # Strip output_path from task_json so the agent can't shortcut by writing
    # pending_turns.json directly. The agent's job is per-turn files; merge_reply.py
    # produces pending_turns.json downstream.
    sanitized_item = {k: v for k, v in item.items() if k != "output_path"}

    extra = [
        f"Dialogue ID: {dialogue_id}",
        f"Narrator voice: {cfg.narrator_voice}",
        "",
        "OUTPUT CONTRACT — read carefully:",
        f"- Write ONE file per plan turn: infrastructure/dialogues/{dialogue_id}/reply_turn_0.json,",
        f"  reply_turn_1.json, ..., reply_turn_{{N-1}}.json (where N = len(reply_plan.turns)).",
        "- DO NOT write pending_turns.json. The orchestrator runs merge_reply.py after you finish",
        "  to assemble pending_turns.json from your per-turn files.",
        "- Do not skip turns. Every entry in reply_plan.turns[] gets a matching reply_turn_{i}.json.",
    ]
    prompt = build_prompt(
        instruction_file="application/dialogue/expand_round_narrator.md",
        task_json=sanitized_item,
        required_reads=required,
        absent_confirmed=absent,
        extra_lines=extra,
    )
    result = await spawn_agent(
        prompt, model="haiku", label="phase2 narrator-batch",
        thinking_budget="off",
        dialogue_id=dialogue_id,
    )
    if result.is_error:
        raise RuntimeError(f"expand_round_narrator agent error: {result.text[:500]}")

    # Refresh preview after all turns landed
    subprocess.run(
        [sys.executable, "application/scripts/preview_turn.py",
         "--dialogue-id", dialogue_id],
        cwd=str(REPO),
        check=True,
    )


# ─── Normal mode ────────────────────────────────────────────────────────────

async def _run_normal(dialogue_id: str, item: dict[str, Any], cfg: TavernConfig) -> None:
    # Build turn context caches (one per turn)
    subprocess.run(
        [sys.executable, "application/scripts/build_turn_context.py",
         "--dialogue-id", dialogue_id],
        cwd=str(REPO),
        check=True,
    )

    plan_path = REPO / "infrastructure" / "dialogues" / dialogue_id / "reply_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    n_turns = len(plan.get("turns", []))
    if n_turns == 0:
        raise RuntimeError(f"reply_plan.json has no turns for dialogue {dialogue_id}")

    for i in range(n_turns):
        await _spawn_normal_turn(dialogue_id, item, i, n_turns)
        subprocess.run(
            [sys.executable, "application/scripts/preview_turn.py",
             "--dialogue-id", dialogue_id],
            cwd=str(REPO),
            check=True,
        )


async def _spawn_normal_turn(dialogue_id: str, item: dict[str, Any], i: int, n_turns: int) -> None:
    base = [f"infrastructure/dialogues/{dialogue_id}/turn_context_{i}.json"]
    optional: list[str] = [
        "application/dialogue/generate_reply_turn.overwrite.md",
    ]
    if i == 0:
        optional.append(f"infrastructure/dialogues/{dialogue_id}/last_turn.json")
        optional.append(f"infrastructure/dialogues/{dialogue_id}/tbc.json")
    else:
        # Prior reply_turn files this round are required (already written by prior spawns).
        for j in range(i):
            base.append(f"infrastructure/dialogues/{dialogue_id}/reply_turn_{j}.json")

    required, absent = build_required_reads(base=base, optional=optional)

    # Strip output_path so the agent can't shortcut to pending_turns.json.
    sanitized_item = {k: v for k, v in item.items() if k != "output_path"}

    extra = [
        f"Turn index: {i}",
        "",
        "OUTPUT CONTRACT:",
        f"- Write ONLY infrastructure/dialogues/{dialogue_id}/reply_turn_{i}.json.",
        "- DO NOT write pending_turns.json — merge_reply.py builds it from your file.",
    ]
    prompt = build_prompt(
        instruction_file="application/dialogue/generate_reply_turn.md",
        task_json=sanitized_item,
        required_reads=required,
        absent_confirmed=absent,
        extra_lines=extra,
    )
    result = await spawn_agent(
        prompt, model="sonnet", label=f"phase2 turn[{i}/{n_turns}]",
        thinking_budget="adaptive",
        dialogue_id=dialogue_id,
    )
    if result.is_error:
        raise RuntimeError(f"normal turn {i} agent error: {result.text[:500]}")
