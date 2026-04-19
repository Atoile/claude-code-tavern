#!/usr/bin/env python3
"""
apply_verbatim.py — Materializes verbatim turns from reply_plan.json into reply_turn_<i>.json files.

Usage:
    python application/scripts/apply_verbatim.py --dialogue-id <id>

Reads:
    infrastructure/dialogues/<id>/reply_plan.json

Writes (one file per verbatim turn in the plan):
    infrastructure/dialogues/<id>/reply_turn_<i>.json
        Schema: {"speaker": "<turns[i].speaker>", "text": "<turns[i].text>"}

If no verbatim turns are present, the script is a no-op and exits cleanly. This makes
it safe to run unconditionally in Phase 2 prep — it only acts when there are verbatim
turns to materialize, eliminating the need for the orchestrator to check the plan and
construct the file by hand.
"""

import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    plan_path = os.path.join(dialogue_dir, "reply_plan.json")

    if not os.path.exists(plan_path):
        print(f"ERROR: reply_plan.json not found at {plan_path}", file=sys.stderr)
        sys.exit(1)

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    turns = plan.get("turns", [])
    if not turns:
        print("OK: no turns in reply_plan.json, nothing to do")
        return

    materialized = 0
    for i, turn in enumerate(turns):
        if not turn.get("verbatim"):
            continue
        speaker = turn.get("speaker")
        text = turn.get("text")
        if not speaker or text is None:
            print(
                f"ERROR: verbatim turn {i} missing speaker or text (speaker={speaker!r})",
                file=sys.stderr,
            )
            sys.exit(1)
        out_path = os.path.join(dialogue_dir, f"reply_turn_{i}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"speaker": speaker, "text": text}, f, ensure_ascii=False, indent=2)
        materialized += 1
        print(f"OK: materialized verbatim turn {i} (speaker={speaker}) to reply_turn_{i}.json")

    if materialized == 0:
        print("OK: no verbatim turns in plan, nothing to do")


if __name__ == "__main__":
    main()
