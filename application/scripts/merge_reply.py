#!/usr/bin/env python3
"""
merge_reply.py — Assembles the final pending_turns.json from the 3-phase pipeline.

Usage:
    python application/scripts/merge_reply.py --dialogue-id <id> --output-path <path>

Reads:
    infrastructure/dialogues/<id>/reply_plan.json    (plan with turn_order + turn_state)
    infrastructure/dialogues/<id>/reply_expand.json  (first character's prose)
    infrastructure/dialogues/<id>/reply_respond.json (second character's prose, single-turn plans only have expand)

Writes:
    <output-path>  (final { "turns": [...], "turn_state": ... } for append_turns.py)

Also appends the plan's summaries to reply_history.json (rolling buffer, last 5 rounds).
Deletes all intermediate files on success.
"""

import argparse
import json
import os
import sys

HISTORY_MAX_ROUNDS = 5


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    plan_path = os.path.join(dialogue_dir, "reply_plan.json")
    expand_path = os.path.join(dialogue_dir, "reply_expand.json")
    respond_path = os.path.join(dialogue_dir, "reply_respond.json")

    for path in (plan_path, expand_path):
        if not os.path.exists(path):
            print(f"ERROR: required file not found: {path}", file=sys.stderr)
            sys.exit(1)

    plan = load_json(plan_path)
    expand = load_json(expand_path)
    single_turn = not os.path.exists(respond_path)

    # Verbatim turns (first-turn mode) are already in the chat — exclude from output
    verbatim_speakers = {
        t["speaker"] for t in plan.get("turns", []) if t.get("verbatim")
    }

    if single_turn:
        turns = [expand]
    else:
        respond = load_json(respond_path)
        turn_order = plan.get("turn_order", [])
        if expand.get("speaker") == turn_order[0]:
            turns = [expand, respond]
        else:
            turns = [respond, expand]

    turns = [t for t in turns if t.get("speaker") not in verbatim_speakers]

    output = {"turns": turns}

    # Include turn_state from plan if present
    turn_state = plan.get("turn_state")
    if turn_state is not None:
        output["turn_state"] = turn_state

    write_json(args.output_path, output)

    # Append plan summaries to reply_history.json (rolling buffer)
    history_path = os.path.join(dialogue_dir, "reply_history.json")
    history = load_json(history_path) if os.path.exists(history_path) else []

    round_entry = {
        "scene_context": plan.get("scene_context_summary", ""),
        "turns": [
            {"speaker": t["speaker"], "summary": t.get("summary") or t.get("text", "")}
            for t in plan.get("turns", [])
        ],
    }
    history.append(round_entry)
    history = history[-HISTORY_MAX_ROUNDS:]
    write_json(history_path, history)

    # Clean up intermediate files
    os.remove(plan_path)
    os.remove(expand_path)
    if not single_turn:
        os.remove(respond_path)
    prose_tail_path = os.path.join(dialogue_dir, "prose_tail.json")
    if os.path.exists(prose_tail_path):
        os.remove(prose_tail_path)

    print(f"OK: merged {len(turns)} turns to {args.output_path}")


if __name__ == "__main__":
    main()
