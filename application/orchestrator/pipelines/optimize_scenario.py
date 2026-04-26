"""optimize_scenario pipeline.

A single Sonnet spawn — generates a participant-tailored scenario after
character selection. Reads each participant's data.json and writes scenario.json.

The frontend (SceneSetupPanel.svelte) POSTs to /api/dialogue/{id}/characters
BEFORE queuing this task — vite's handler mkdirs the dialogue dir and writes
the initial characters.json with the participants dict. By the time the
orchestrator dispatches us, both already exist.
"""

from __future__ import annotations

from typing import Any

from ..env import TavernConfig
from ..prompts import REPO, build_prompt, build_required_reads
from ..sdk import spawn_agent


_OPTIONAL = [
    "application/dialogue/optimize_scenario.overwrite.md",
]


def _dialogue_id_from(item: dict[str, Any]) -> str:
    """Pull the dialogue_id out of the queue item's output_path.

    output_path looks like infrastructure/dialogues/{dialogue_id}/scenario.json
    so the parent dir's name IS the dialogue_id.
    """
    output_path = item["output_path"]
    return (REPO / output_path).parent.name


async def run(item: dict[str, Any], cfg: TavernConfig) -> None:
    dialogue_id = _dialogue_id_from(item)

    required, absent = build_required_reads(base=[], optional=_OPTIONAL)
    prompt = build_prompt(
        instruction_file="application/dialogue/optimize_scenario.md",
        task_json=item,
        required_reads=required if required else None,
        absent_confirmed=absent if absent else None,
        extra_lines=[
            "OUTPUT CONTRACT:",
            "- The orchestrator already created the dialogue directory and",
            "  wrote the initial characters.json with the participants dict.",
            "- Your ONLY job is to write the scenario file at task_json.output_path.",
            "- Do NOT mkdir, do NOT write characters.json, do NOT touch any other file.",
        ],
    )
    result = await spawn_agent(
        prompt, model="sonnet", label="optimize_scenario",
        thinking_budget="adaptive",
        dialogue_id=dialogue_id,
    )
    if result.is_error:
        raise RuntimeError(f"optimize_scenario agent reported error: {result.text[:500]}")
