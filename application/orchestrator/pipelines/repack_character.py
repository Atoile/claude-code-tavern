"""repack_character pipeline.

A single Sonnet spawn with the repack agent instructions. The agent itself
runs card_extract.py first to materialize legacy.json + avatar.png, then
synthesizes the result into data.json at the task's output_path.

Step 1 scope: no Tier 1 manifest (deferred to Step 2). Static prompt.
"""

from __future__ import annotations

from typing import Any

from ..env import TavernConfig
from ..prompts import build_prompt, build_required_reads
from ..sdk import spawn_agent


_OPTIONAL = [
    "application/character/repack.overwrite.md",
]


async def run(item: dict[str, Any], cfg: TavernConfig) -> None:
    required, absent = build_required_reads(base=[], optional=_OPTIONAL)
    prompt = build_prompt(
        instruction_file="application/character/repack.md",
        task_json=item,
        required_reads=required if required else None,
        absent_confirmed=absent if absent else None,
    )
    result = await spawn_agent(prompt, model="sonnet", label="repack")
    if result.is_error:
        raise RuntimeError(f"repack_character agent reported error: {result.text[:500]}")
