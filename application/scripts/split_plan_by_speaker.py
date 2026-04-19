#!/usr/bin/env python3
"""
split_plan_by_speaker.py — Splits reply_plan.json into per-speaker slices.

Reads the narrator-mode plan and writes one slice file per unique speaker,
each containing ONLY that speaker's turns, brief, and voice data. The
orchestrator uses these to spawn per-character agents with minimal context.

Usage:
    python application/scripts/split_plan_by_speaker.py --dialogue-id <id>

Writes:
    infrastructure/dialogues/<id>/plan_slice_<speaker>.json

Each slice contains:
{
  "speaker": "<char_id or _narrator>",
  "turn_indices": [0, 3, 5],          // which indices in turn_order are mine
  "turns": [ {beat entries} ],         // only my turns
  "brief": { ... } | null,            // my character_brief (null for narrator)
  "scene_context_summary": "...",
  "round_protagonist": "...",
  "narrator_voice": null               // set only for _narrator slice
}
"""

import argparse
import json
import os
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    parser.add_argument("--narrator-voice", default="neutral")
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    plan_path = os.path.join(dialogue_dir, "reply_plan.json")

    if not os.path.exists(plan_path):
        print(f"ERROR: reply_plan.json not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    plan = load_json(plan_path)
    turns = plan.get("turns", [])
    turn_order = plan.get("turn_order", [])
    briefs = plan.get("character_briefs", {})
    scene_ctx = plan.get("scene_context_summary", "")
    protagonist = plan.get("round_protagonist", "")

    # Group turns by speaker
    speakers = {}
    for i, turn in enumerate(turns):
        speaker = turn.get("speaker", "")
        if speaker not in speakers:
            speakers[speaker] = {"indices": [], "turns": []}
        speakers[speaker]["indices"].append(i)
        speakers[speaker]["turns"].append(turn)

    # Write per-speaker slice files
    written = []
    for speaker, data in speakers.items():
        slice_data = {
            "speaker": speaker,
            "turn_indices": data["indices"],
            "turns": data["turns"],
            "brief": briefs.get(speaker) if speaker != "_narrator" else None,
            "scene_context_summary": scene_ctx,
            "round_protagonist": protagonist,
        }
        if speaker == "_narrator":
            slice_data["narrator_voice"] = args.narrator_voice

        slice_path = os.path.join(dialogue_dir, f"plan_slice_{speaker}.json")
        write_json(slice_path, slice_data)
        written.append(speaker)

    # Also write the turn_order so the orchestrator knows the sequence
    order_path = os.path.join(dialogue_dir, "plan_turn_order.json")
    write_json(order_path, turn_order)

    print(f"OK: split plan into {len(written)} slices: {', '.join(written)}")


if __name__ == "__main__":
    main()
