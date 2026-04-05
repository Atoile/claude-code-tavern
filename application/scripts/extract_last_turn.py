#!/usr/bin/env python3
"""
extract_last_turn.py — Extracts the last turn from recent_chat.json for expand agent reaction context.

Usage:
    python application/scripts/extract_last_turn.py --dialogue-id <id>

Writes:
    infrastructure/dialogues/<id>/last_turn.json

Single turn object (full text, no truncation) so the expand agent knows exactly
what it is reacting to in sequential mode.
"""

import argparse
import json
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    recent_path = os.path.join(dialogue_dir, "recent_chat.json")
    output_path = os.path.join(dialogue_dir, "last_turn.json")

    if not os.path.exists(recent_path):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(None, f)
        print("OK: no recent_chat.json, wrote null last_turn.json")
        return

    with open(recent_path, "r", encoding="utf-8") as f:
        chat = json.load(f)

    last = chat[-1] if chat else None

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(last, f, ensure_ascii=False, indent=2)

    if last:
        print(f"OK: extracted last turn (char_id={last.get('char_id', '?')}) to last_turn.json")
    else:
        print("OK: recent_chat.json is empty, wrote null last_turn.json")


if __name__ == "__main__":
    main()
