#!/usr/bin/env python3
"""
append_turns.py — Appends newly generated turns to full_chat.json and recent_chat.json.

Usage:
    python application/scripts/append_turns.py --dialogue-id <id> --turns-file <path> [--user-prompt <text>]

Turns file format (new):
    { "turns": [ turn objects ], "turn_state": { ... } }

Turns file format (legacy):
    [ turn objects ]

- Reads new turns from <turns-file>
- Appends to infrastructure/dialogues/<id>/full_chat.json  (unbounded permanent record)
- Appends to infrastructure/dialogues/<id>/recent_chat.json (trimmed to last 10)
- Writes turn_state.json if turn_state is present in output; deletes it if absent
- Deletes <turns-file> on success
"""

import argparse
import json
import os
import sys

RECENT_CHAT_TRIM = 10
HISTORY_MAX_ROUNDS = 5


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
    parser.add_argument("--user-prompt", default=None)
    args = parser.parse_args()

    turns_file = args.turns_file
    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    full_chat_path = os.path.join(dialogue_dir, "full_chat.json")
    recent_chat_path = os.path.join(dialogue_dir, "recent_chat.json")
    turn_state_path = os.path.join(dialogue_dir, "turn_state.json")

    if not os.path.exists(turns_file):
        print(f"ERROR: turns file not found: {turns_file}", file=sys.stderr)
        sys.exit(1)

    with open(turns_file, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Support both new { "turns": [...], "turn_state": {...} } and legacy [...] formats
    if isinstance(payload, dict):
        new_turns = payload.get("turns", [])
        turn_state = payload.get("turn_state")
    else:
        new_turns = payload if isinstance(payload, list) else [payload]
        turn_state = None

    # Snapshot turn_state onto the last turn so rollback can restore it exactly
    if new_turns:
        new_turns[-1]["_state"] = turn_state  # None means no active state

    # Store user_prompt on the first turn so rollback can restore it to the direction input
    if new_turns and args.user_prompt:
        new_turns[0]["_prompt"] = args.user_prompt

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

    # Write or delete turn_state.json
    if turn_state is not None:
        write_json(turn_state_path, turn_state)
    elif os.path.exists(turn_state_path):
        os.remove(turn_state_path)

    os.remove(turns_file)

    # Seed reply_history.json if it doesn't exist yet (opening lines bypass merge_reply.py)
    history_path = os.path.join(dialogue_dir, "reply_history.json")
    if not os.path.exists(history_path):
        seed_entry = {
            "scene_context": "",
            "turns": [{"speaker": t["speaker"], "summary": t["text"]} for t in new_turns],
        }
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump([seed_entry], f, ensure_ascii=False, indent=2)

    # Signal when turns have fallen off recent_chat and a full batch has accumulated
    # Skips the premature first trigger at full_chat=RECENT_CHAT_TRIM (nothing outside context yet)
    if new_full_chat_len > RECENT_CHAT_TRIM and new_full_chat_len // 10 > prev_full_chat_len // 10:
        print(f"CONDENSE_NEEDED {args.dialogue_id}")
    else:
        print(
            f"OK: {len(new_turns)} turn(s) appended to {args.dialogue_id} | "
            f"full_chat={new_full_chat_len} recent_chat={len(recent_chat)}"
        )


if __name__ == "__main__":
    main()
