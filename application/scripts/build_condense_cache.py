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

import argparse
import json
import os
import sys


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    if not os.path.isdir(dialogue_dir):
        print(f"ERROR: dialogue dir not found: {dialogue_dir}", file=sys.stderr)
        sys.exit(1)

    # Full chat — extract batch
    full_chat = load_json(os.path.join(dialogue_dir, "full_chat.json")) or []
    memory = load_json(os.path.join(dialogue_dir, "memory.json"))
    condensed_through = 0
    if memory:
        condensed_through = memory.get("condensed_through", 0)

    batch = full_chat[condensed_through:]
    if not batch:
        print(f"OK: nothing to condense (condensed_through={condensed_through}, full_chat={len(full_chat)})")
        sys.exit(0)

    # Recent chat
    recent_chat = load_json(os.path.join(dialogue_dir, "recent_chat.json")) or []

    # Characters
    characters_data = load_json(os.path.join(dialogue_dir, "characters.json")) or {}
    participants = characters_data.get("participants", {})

    # Scenario
    scenario = load_json(os.path.join(dialogue_dir, "scenario.json"))
    scenario_summary = None
    if scenario:
        leading_id = characters_data.get("leading_id")
        sp = scenario.get("participants", {})
        if leading_id and leading_id in sp:
            scenario_summary = sp[leading_id].get("scenario")
        elif sp:
            scenario_summary = next(iter(sp.values()), {}).get("scenario")

    # Character identity/personality from data.json
    char_profiles = {}
    for char_id, pdata in participants.items():
        data_path = pdata.get("data_path")
        if not data_path:
            continue
        char_data = load_json(data_path)
        if not char_data:
            continue
        personality = char_data.get("personality", {})
        char_profiles[char_id] = {
            "name": char_data.get("meta", {}).get("name", char_id),
            "core_traits": personality.get("core_traits", []),
            "emotional_baseline": personality.get("emotional_baseline", ""),
        }

    # Build cache
    cache = {
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
