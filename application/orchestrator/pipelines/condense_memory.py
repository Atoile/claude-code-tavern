"""condense_memory pipeline.

Triggered inline by generate_reply pipeline when append_turns.py outputs
CONDENSE_NEEDED. Reads condense_cache.json (built by build_condense_cache.py)
and writes memory.json + short_memory.json + memory_checkpoint.json.

Step 1 scope: no Tier 1 manifest (deferred to Step 2). Static prompt.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from ..env import TavernConfig
from ..prompts import REPO, build_prompt, build_required_reads
from ..sdk import spawn_agent


_BASE = [
    "infrastructure/dialogues/{dialogue_id}/condense_cache.json",
]
_OPTIONAL = [
    "application/dialogue/condense_memory.overwrite.md",
]


async def run_inline(dialogue_id: str, cfg: TavernConfig) -> None:
    """Build the condense cache and spawn the agent. Used by generate_reply."""
    subprocess.run(
        [sys.executable, "application/scripts/build_condense_cache.py",
         "--dialogue-id", dialogue_id],
        cwd=str(REPO),
        check=True,
    )

    required, absent = build_required_reads(
        base=_BASE, optional=_OPTIONAL, dialogue_id=dialogue_id,
    )
    task_json = {"type": "condense_memory", "input": {"dialogue_id": dialogue_id}}
    prompt = build_prompt(
        instruction_file="application/dialogue/condense_memory.md",
        task_json=task_json,
        required_reads=required,
        absent_confirmed=absent,
    )
    result = await spawn_agent(prompt, model="sonnet", label="condense_memory", dialogue_id=dialogue_id)
    if result.is_error:
        raise RuntimeError(f"condense_memory agent reported error: {result.text[:500]}")


async def run(item: dict[str, Any], cfg: TavernConfig) -> None:
    """Direct queue dispatch — uncommon; usually condense fires inline."""
    dialogue_id = item["input"]["dialogue_id"]
    await run_inline(dialogue_id, cfg)
