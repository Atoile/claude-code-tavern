"""Per-task-type pipeline dispatch."""

from __future__ import annotations

from typing import Any

from ..env import TavernConfig

# Task type → pipeline coroutine
# Resolved lazily to avoid heavy imports at module load.


async def dispatch(item: dict[str, Any], cfg: TavernConfig) -> None:
    """Run the pipeline for one queue item. Raises on failure."""
    task_type = item.get("type")
    if task_type == "repack_character":
        from .repack_character import run as run_repack
        await run_repack(item, cfg)
    elif task_type == "optimize_scenario":
        from .optimize_scenario import run as run_optimize
        await run_optimize(item, cfg)
    elif task_type == "condense_memory":
        from .condense_memory import run as run_condense
        await run_condense(item, cfg)
    elif task_type == "generate_reply":
        from .generate_reply import run as run_generate_reply
        await run_generate_reply(item, cfg)
    else:
        raise ValueError(f"no pipeline defined for task type {task_type!r}")
