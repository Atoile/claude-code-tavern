#!/usr/bin/env python3
"""
append_turns.py — Appends newly generated turns to full_chat.json and recent_chat.json.

Usage:
    python application/scripts/append_turns.py --dialogue-id <id> --turns-file <path>

- Reads new turns from <turns-file> (JSON array of turn objects)
- Appends to infrastructure/dialogues/<id>/full_chat.json  (unbounded permanent record)
- Appends to infrastructure/dialogues/<id>/recent_chat.json (trimmed to last 10)
- Deletes <turns-file> on success
"""

import argparse
import json
import os
import sys

RECENT_CHAT_TRIM = 10


def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    parser.add_argument("--turns-file", required=True)
    args = parser.parse_args()

    turns_file = args.turns_file
    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    full_chat_path = os.path.join(dialogue_dir, "full_chat.json")
    recent_chat_path = os.path.join(dialogue_dir, "recent_chat.json")

    if not os.path.exists(turns_file):
        print(f"ERROR: turns file not found: {turns_file}", file=sys.stderr)
        sys.exit(1)

    with open(turns_file, "r", encoding="utf-8") as f:
        new_turns = json.load(f)
    if not isinstance(new_turns, list):
        new_turns = [new_turns]

    # Append to full_chat (unbounded)
    full_chat = load_json(full_chat_path)
    prev_full_chat_len = len(full_chat)
    full_chat.extend(new_turns)
    new_full_chat_len = len(full_chat)
    write_json(full_chat_path, full_chat)

    # Append to recent_chat and trim
    recent_chat = load_json(recent_chat_path)
    recent_chat.extend(new_turns)
    recent_chat = recent_chat[-RECENT_CHAT_TRIM:]
    write_json(recent_chat_path, recent_chat)

    os.remove(turns_file)

    # Signal if a condensing cycle has been crossed (every 10 entries)
    if new_full_chat_len >= 10 and new_full_chat_len // 10 > prev_full_chat_len // 10:
        print(f"CONDENSE_NEEDED {args.dialogue_id}")
    else:
        print(
            f"OK: {len(new_turns)} turn(s) appended to {args.dialogue_id} | "
            f"full_chat={new_full_chat_len} recent_chat={len(recent_chat)}"
        )


if __name__ == "__main__":
    main()
