#!/usr/bin/env python3
"""
preview_turn.py — Rebuilds preview_turn.json from whatever reply_turn_<i>.json files exist.

Usage:
    python application/scripts/preview_turn.py --dialogue-id <id>

Reads:
    infrastructure/dialogues/<id>/reply_plan.json     (for turn order, optional)
    infrastructure/dialogues/<id>/reply_turn_<i>.json (every file present)

Writes:
    infrastructure/dialogues/<id>/preview_turn.json
        [ { "speaker", "text", "_preview": true }, ... ]

This script is the orchestrator's UI-preview hook. Run it after each turn agent
completes (Phase 2, between turn dispatches) to refresh the preview the UI polls
while a multi-turn round is being generated.

Walks `reply_plan.turns[]` in order and includes each turn whose `reply_turn_<i>.json`
file is on disk. If no plan exists, walks `reply_turn_*.json` in numeric order. Safe
to run repeatedly and at any point in the pipeline. Exits cleanly with a SKIP message
if no turn files are found yet. The file is cleaned up automatically by `append_turns.py`
on successful append.
"""

import argparse
import json
import os
import re


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    plan_path = os.path.join(dialogue_dir, "reply_plan.json")
    preview_path = os.path.join(dialogue_dir, "preview_turn.json")

    # Determine the ordered list of turn indices to read
    if os.path.exists(plan_path):
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        turn_indices = list(range(len(plan.get("turns", []))))
    else:
        # No plan — walk reply_turn_<i>.json files in numeric order
        pattern = re.compile(r"^reply_turn_(\d+)\.json$")
        indices = []
        if os.path.isdir(dialogue_dir):
            for entry in os.listdir(dialogue_dir):
                m = pattern.match(entry)
                if m:
                    indices.append(int(m.group(1)))
        turn_indices = sorted(indices)

    preview = []
    for i in turn_indices:
        turn_path = os.path.join(dialogue_dir, f"reply_turn_{i}.json")
        if not os.path.exists(turn_path):
            continue  # not yet written — skip; later runs will pick it up
        with open(turn_path, "r", encoding="utf-8") as f:
            turn = json.load(f)
        preview.append({
            "speaker": turn.get("speaker", ""),
            "text": turn.get("text", ""),
            "_preview": True,
        })

    if not preview:
        print("SKIP: no reply_turn_*.json files found")
        return

    with open(preview_path, "w", encoding="utf-8") as f:
        json.dump(preview, f, ensure_ascii=False, indent=2)

    print(f"OK: preview_turn.json updated with {len(preview)} turn(s)")


if __name__ == "__main__":
    main()
