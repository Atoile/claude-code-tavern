"""Prompt construction with Tier 1 manifest mechanism.

Tier 1: the orchestrator probes os.path.exists() in Python (free, no tokens) and
builds the prompt's Required reads block from filesystem state. Files that are
absent get listed in a separate "confirmed absent" block so the agent doesn't
probe for them. Agents are told the manifest is the COMPLETE list of files to
read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]


def resolve(rel: str, dialogue_id: str | None = None) -> Path:
    """Format a relative path template and resolve it against the repo root."""
    if dialogue_id is not None and "{dialogue_id}" in rel:
        rel = rel.format(dialogue_id=dialogue_id)
    return REPO / rel


def split_existing(rel_paths: list[str], dialogue_id: str | None = None) -> tuple[list[str], list[str]]:
    """Partition `rel_paths` into (present, absent) by os.path.exists()."""
    present: list[str] = []
    absent: list[str] = []
    for rel in rel_paths:
        formatted = rel.format(dialogue_id=dialogue_id) if dialogue_id and "{dialogue_id}" in rel else rel
        if (REPO / formatted).exists():
            present.append(formatted)
        else:
            absent.append(formatted)
    return present, absent


def build_required_reads(
    base: list[str],
    optional: list[str],
    dialogue_id: str | None = None,
) -> tuple[list[str], list[str]]:
    """Return (required_reads, absent_confirmed) — formatted relative paths.

    base = reads that are always required (must exist or the spawn fails)
    optional = reads that may or may not exist — Tier 1 probes them
    """
    base_paths = [
        rel.format(dialogue_id=dialogue_id) if dialogue_id and "{dialogue_id}" in rel else rel
        for rel in base
    ]
    present, absent = split_existing(optional, dialogue_id)
    return base_paths + present, absent


def build_prompt(
    instruction_file: str,
    task_json: dict[str, Any] | None = None,
    required_reads: list[str] | None = None,
    absent_confirmed: list[str] | None = None,
    extra_lines: list[str] | None = None,
) -> str:
    """Compose a self-contained agent prompt.

    Layout:
      Read your instructions from <instruction_file> and execute the task.

      Task input (exact queue item):
      <task_json>

      Required reads — these are the COMPLETE list of files for this spawn.
      Read every one. Do not Read, Glob, or Bash-stat any other path.
      - <path>
      - ...

      Files checked and confirmed absent (DO NOT probe — they are not on disk):
      - <path>
      - ...

      <extra_lines...>

      Working directory is the repository root.
      Platform: Windows; repo root d:/AI/Tavern.
    """
    parts: list[str] = [
        f"Read your instructions from {instruction_file} and execute the task.",
    ]

    if task_json is not None:
        parts.append("")
        parts.append("Task input (exact queue item):")
        parts.append(json.dumps(task_json, indent=2, ensure_ascii=False))

    if required_reads:
        parts.append("")
        parts.append(
            "Required reads — these are the COMPLETE list of files for this spawn. "
            "Read every one. Do not Read, Glob, or Bash-stat any other path."
        )
        for rel in required_reads:
            parts.append(f"- {rel}")

    if absent_confirmed:
        parts.append("")
        parts.append(
            "Files checked and confirmed absent (DO NOT probe — they are not on disk):"
        )
        for rel in absent_confirmed:
            parts.append(f"- {rel}")

    if extra_lines:
        parts.append("")
        parts.extend(extra_lines)

    parts.append("")
    parts.append("Working directory is the repository root.")
    parts.append("Platform: Windows; repo root d:/AI/Tavern.")
    parts.append("")
    parts.append(
        "Output discipline: be terse. Do NOT narrate your process "
        "(no 'Now let me read X', no 'I have everything I need', no post-write "
        "summaries). The orchestrator already logs every tool call and the final "
        "result. Use tools, write files, exit. Every commentary token is wasted spend."
    )

    return "\n".join(parts)


def per_character_context_caches(dialogue_id: str) -> list[str]:
    """List existing context_cache_<char_id>.json files for a dialogue."""
    dlg_dir = REPO / "infrastructure" / "dialogues" / dialogue_id
    if not dlg_dir.exists():
        return []
    out: list[str] = []
    for p in sorted(dlg_dir.glob("context_cache_*.json")):
        if p.name == "context_cache.json":
            continue
        out.append(f"infrastructure/dialogues/{dialogue_id}/{p.name}")
    return out
