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
- Appends to infrastructure/dialogues/<id>/recent_chat.json (trimmed to last RECENT_CHAT_TRIM entries)
- Writes turn_state.json if turn_state is present in output; deletes it if absent
- Deletes <turns-file> on success
"""

import argparse
import json
import os
import sys

RECENT_CHAT_TRIM = 30
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
        dialogue_complete = payload.get("dialogue_complete", False)
        goal_resolution = payload.get("goal_resolution")
    else:
        new_turns = payload if isinstance(payload, list) else [payload]
        turn_state = None
        dialogue_complete = False
        goal_resolution = None

    # Snapshot turn_state onto the last turn so rollback can restore it exactly
    if new_turns:
        new_turns[-1]["_state"] = turn_state  # None means no active state

    # Store user_prompt on the first turn so rollback can restore it to the direction input
    if new_turns and args.user_prompt:
        new_turns[0]["_prompt"] = args.user_prompt

    # Append to full_chat (unbounded)
    full_chat = load_json(full_chat_path)
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

    # Clean up preview_turn.json if it exists (written by preview_expand.py for early UI display)
    preview_path = os.path.join(dialogue_dir, "preview_turn.json")
    if os.path.exists(preview_path):
        os.remove(preview_path)

    # Seed reply_history.json if it doesn't exist yet (defensive — normally merge_reply.py
    # creates it in Phase 3 before this script runs). Flat per-turn format: one entry per
    # turn, scene_context only on the first entry of a round.
    history_path = os.path.join(dialogue_dir, "reply_history.json")
    if not os.path.exists(history_path) and new_turns:
        seed = []
        for idx, t in enumerate(new_turns):
            entry = {"speaker": t["speaker"], "summary": t["text"]}
            if idx == 0:
                entry["scene_context"] = ""
            seed.append(entry)
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(seed, f, ensure_ascii=False, indent=2)

    # Smart condense trigger — only condense when there's enough new content to justify it
    condense = False

    if new_full_chat_len > RECENT_CHAT_TRIM:
        # Check how many turns since last condense
        memory_path = os.path.join(dialogue_dir, "memory.json")
        last_condensed = 0
        if os.path.exists(memory_path):
            with open(memory_path, "r", encoding="utf-8") as f:
                mem = json.load(f)
                last_condensed = mem.get("condensed_through", 0)

        turns_since_condense = new_full_chat_len - last_condensed

        # Count word content in the new turns being appended
        new_words = sum(len(t.get("text", "").split()) for t in new_turns)

        # Minimum 10 turns between condensations — baseline for all triggers
        MIN_TURNS_BETWEEN_CONDENSE = 10

        # Context loss prevention: turns that fell off recent_chat but aren't in memory
        # Only trigger when the gap is significant (10+ uncovered turns)
        uncovered_gap = max(0, (new_full_chat_len - RECENT_CHAT_TRIM) - last_condensed)

        if uncovered_gap >= MIN_TURNS_BETWEEN_CONDENSE:
            condense = True
        elif turns_since_condense >= 20:
            condense = True
        elif new_words >= 500 and turns_since_condense >= MIN_TURNS_BETWEEN_CONDENSE:
            condense = True

    # Goal completion — write complete.json and update goals.json
    if dialogue_complete and goal_resolution:
        from datetime import datetime, timezone

        complete_path = os.path.join(dialogue_dir, "complete.json")
        complete_data = {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "goal_id": goal_resolution.get("goal_id"),
            "outcome": goal_resolution.get("outcome"),
            "detail": goal_resolution.get("detail", ""),
        }
        write_json(complete_path, complete_data)

        goals_path = os.path.join(dialogue_dir, "goals.json")
        if os.path.exists(goals_path):
            with open(goals_path, "r", encoding="utf-8") as f:
                goals_data = json.load(f)
            for goal in goals_data.get("goals", []):
                if goal.get("id") == goal_resolution.get("goal_id"):
                    goal["status"] = "resolved"
                    goal["resolved_as"] = goal_resolution.get("outcome")
                    break
            write_json(goals_path, goals_data)

        print(
            f"GOAL_COMPLETED {args.dialogue_id} "
            f"{goal_resolution.get('goal_id')} {goal_resolution.get('outcome')}"
        )

    if condense:
        print(f"CONDENSE_NEEDED {args.dialogue_id}")

    if not dialogue_complete or not goal_resolution:
        print(
            f"OK: {len(new_turns)} turn(s) appended to {args.dialogue_id} | "
            f"full_chat={new_full_chat_len} recent_chat={len(recent_chat)}"
        )


if __name__ == "__main__":
    main()
