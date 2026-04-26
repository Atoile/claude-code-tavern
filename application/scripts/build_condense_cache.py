"""
build_condense_cache.py — Collects all data needed for memory condensation into a single cache file.

Usage:
    python application/scripts/build_condense_cache.py --dialogue-id <id>

Reads:
    - full_chat.json (extracts batch from condensed_through to end)
    - memory.json (existing cumulative memory, if any)
    - recent_chat.json (for short_memory generation)
    - characters.json (participant set)
    - scenario.json (scene premise)
    - Each participant's data.json (name, core_traits, emotional_baseline only)

Writes:
    - infrastructure/dialogues/<id>/condense_cache.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, cast


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    if not os.path.isdir(dialogue_dir):
        print(f"ERROR: dialogue dir not found: {dialogue_dir}", file=sys.stderr)
        sys.exit(1)

    # Full chat — extract batch
    full_chat_raw: Any = load_json(os.path.join(dialogue_dir, "full_chat.json")) or []
    full_chat: list[Any] = cast(list[Any], full_chat_raw) if isinstance(full_chat_raw, list) else []
    memory_raw: Any = load_json(os.path.join(dialogue_dir, "memory.json"))
    memory: dict[str, Any] | None = (
        cast(dict[str, Any], memory_raw) if isinstance(memory_raw, dict) else None
    )
    condensed_through: int = 0
    if memory:
        ct: Any = memory.get("condensed_through", 0)
        condensed_through = ct if isinstance(ct, int) else 0

    batch = full_chat[condensed_through:]
    if not batch:
        print(f"OK: nothing to condense (condensed_through={condensed_through}, full_chat={len(full_chat)})")
        sys.exit(0)

    # Recent chat
    recent_chat_raw: Any = load_json(os.path.join(dialogue_dir, "recent_chat.json")) or []
    recent_chat: list[Any] = (
        cast(list[Any], recent_chat_raw) if isinstance(recent_chat_raw, list) else []
    )

    # Characters
    characters_raw: Any = load_json(os.path.join(dialogue_dir, "characters.json")) or {}
    characters_data: dict[str, Any] = (
        cast(dict[str, Any], characters_raw) if isinstance(characters_raw, dict) else {}
    )
    participants_raw: Any = characters_data.get("participants", {})
    participants: dict[str, Any] = (
        cast(dict[str, Any], participants_raw) if isinstance(participants_raw, dict) else {}
    )

    # Scenario
    scenario_raw: Any = load_json(os.path.join(dialogue_dir, "scenario.json"))
    scenario_summary: Any = None
    if isinstance(scenario_raw, dict):
        scenario: dict[str, Any] = cast(dict[str, Any], scenario_raw)
        leading_id: Any = characters_data.get("leading_id")
        sp_raw: Any = scenario.get("participants", {})
        sp: dict[str, Any] = cast(dict[str, Any], sp_raw) if isinstance(sp_raw, dict) else {}
        if isinstance(leading_id, str) and leading_id in sp:
            entry: Any = sp[leading_id]
            if isinstance(entry, dict):
                scenario_summary = cast(dict[str, Any], entry).get("scenario")
        elif sp:
            first: Any = next(iter(sp.values()), cast(dict[str, Any], {}))
            if isinstance(first, dict):
                scenario_summary = cast(dict[str, Any], first).get("scenario")

    # Character identity/personality from data.json
    char_profiles: dict[str, dict[str, Any]] = {}
    for char_id, pdata_raw in participants.items():
        if not isinstance(pdata_raw, dict):
            continue
        pdata: dict[str, Any] = cast(dict[str, Any], pdata_raw)
        data_path: Any = pdata.get("data_path")
        if not isinstance(data_path, str) or not data_path:
            continue
        char_data_raw: Any = load_json(data_path)
        if not isinstance(char_data_raw, dict):
            continue
        char_data: dict[str, Any] = cast(dict[str, Any], char_data_raw)
        personality_raw: Any = char_data.get("personality", {})
        personality: dict[str, Any] = (
            cast(dict[str, Any], personality_raw) if isinstance(personality_raw, dict) else {}
        )
        meta_raw: Any = char_data.get("meta", {})
        meta: dict[str, Any] = cast(dict[str, Any], meta_raw) if isinstance(meta_raw, dict) else {}
        char_profiles[char_id] = {
            "name": meta.get("name", char_id),
            "core_traits": personality.get("core_traits", []),
            "emotional_baseline": personality.get("emotional_baseline", ""),
        }

    # Build cache
    cache: dict[str, Any] = {
        "dialogue_id": args.dialogue_id,
        "full_chat_len": len(full_chat),
        "condensed_through": condensed_through,
        "batch_range": [condensed_through, len(full_chat)],
        "batch": batch,
        "existing_memory": memory,
        "recent_chat": recent_chat,
        "participants": char_profiles,
        "scenario_summary": scenario_summary,
    }

    out_path = os.path.join(dialogue_dir, "condense_cache.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print(
        f"BUILT: condense_cache.json "
        f"(batch={len(batch)} turns [{condensed_through}..{len(full_chat)}], "
        f"recent_chat={len(recent_chat)}, "
        f"participants={len(char_profiles)})"
    )


if __name__ == "__main__":
    main()
