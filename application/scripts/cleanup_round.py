#!/usr/bin/env python3
"""
cleanup_round.py — Removes intermediate files left after a generate_reply round.

Files already cleaned by other scripts:
    merge_reply.py:       reply_plan.json, reply_turn_*.json, prose_tail.json,
                          plan_slice_*.json, plan_turn_order.json
    append_turns.py:      pending_turns.json, preview_turn.json
    turn_finalization.py: actualized_turn_state.json, actualized_climax_history.json

This script handles the remainder:
    turn_context_*.json   (from build_turn_context.py)
    plan_validation.json  (from validate_plan agent)
    last_turn.json        (from extract_last_turn.py)

Safe to run at any time — skips files that don't exist.

Usage:
    python application/scripts/cleanup_round.py --dialogue-id <id>
"""

import argparse
import glob
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    d = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    if not os.path.isdir(d):
        print(f"SKIP: {d} does not exist")
        return

    removed = 0

    # turn_context_*.json
    for f in glob.glob(os.path.join(d, "turn_context_*.json")):
        os.remove(f)
        removed += 1

    # Single-file intermediates
    for name in ("plan_validation.json", "last_turn.json"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            os.remove(p)
            removed += 1

    print(f"OK: cleaned {removed} intermediate file(s) from {args.dialogue_id}")


if __name__ == "__main__":
    main()
