#!/usr/bin/env python3
"""
extract_prose_tail.py — Extracts truncated tail of the last 2 turns for prose agent voice matching.

Usage:
    python application/scripts/extract_prose_tail.py --dialogue-id <id>

Writes:
    infrastructure/dialogues/<id>/prose_tail.json

Each turn is truncated to the last ~500 characters of text to keep the file small
while giving prose agents enough to match voice and register.
"""

import argparse
import json
import os

TURN_COUNT = 2
CHAR_LIMIT = 500


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    recent_path = os.path.join(dialogue_dir, "recent_chat.json")
    output_path = os.path.join(dialogue_dir, "prose_tail.json")

    if not os.path.exists(recent_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        print("OK: no recent_chat.json, wrote empty prose_tail.json")
        return

    with open(recent_path, "r", encoding="utf-8") as f:
        chat = json.load(f)

    tail = chat[-TURN_COUNT:] if len(chat) > TURN_COUNT else list(chat)

    for turn in tail:
        text = turn.get("text", "")
        if len(text) > CHAR_LIMIT:
            turn["text"] = "..." + text[-CHAR_LIMIT:]
        # Strip _state from prose tail — not needed for voice matching
        turn.pop("_state", None)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tail, f, ensure_ascii=False, indent=2)

    print(f"OK: extracted {len(tail)} truncated turns to prose_tail.json")


if __name__ == "__main__":
    main()
