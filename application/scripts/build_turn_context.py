"""
build_turn_context.py — Builds a single context cache file per turn.

Collapses 6+ agent file reads into 1, eliminating token pyramiding from
sequential tool calls. Run after Phase 1 (plan is written) and before
Phase 2 (turn generation).

Usage:
    python application/scripts/build_turn_context.py --dialogue-id <id>

Reads:
    - reply_plan.json (turn entries, character briefs)
    - active_lorebook_{char_id}.json (per-character lorebook)
    - writing_rules_cache.md (merged writing rules)
    - prose_tail.json (last 2 turns truncated)

Writes:
    - infrastructure/dialogues/<id>/turn_context_{i}.json  (one per turn)

Each cache contains everything the turn agent needs except:
    - The agent instruction files (generate_reply_turn.md + overwrite)
    - Prior turn files (reply_turn_{j}.json) — created sequentially at runtime
    - last_turn.json — small enough to read directly

The agent reads: instructions + turn_context_{i}.json + prior context = 3 reads
instead of: instructions + plan + lorebook + rules + prose_tail + ... = 8+ reads
"""

import argparse
import json
import os
import sys


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    plan_path = os.path.join(dialogue_dir, "reply_plan.json")

    plan = load_json(plan_path)
    if not plan:
        print(f"ERROR: reply_plan.json not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    turns = plan.get("turns", [])

    # Briefs now live in a sidecar file built by build_character_briefs.py in
    # Phase 0 — the planner no longer copies them into reply_plan.json. Fall
    # back to plan.character_briefs if the sidecar is missing (older dialogues
    # whose plans still carry briefs inline).
    briefs_path = os.path.join(dialogue_dir, "character_briefs.json")
    briefs = load_json(briefs_path) or plan.get("character_briefs", {})

    # Writing rules
    writing_rules = load_text("domain/dialogue/writing_rules_cache.md") or ""

    # Prose tail
    prose_tail = load_json(os.path.join(dialogue_dir, "prose_tail.json"))

    # Scene context summary from plan
    scene_context = plan.get("scene_context_summary", "")

    # Scene anchor — load-bearing carryover from prior round's end-state.
    # Turn agents must honor every populated field (time, location, proximity,
    # positions, wardrobe, in_progress_action). Empty-dict fallback for older
    # plans that predate this field.
    scene_anchor = plan.get("scene_anchor") or {}

    built = 0
    for i, turn in enumerate(turns):
        speaker = turn.get("speaker", "")

        # Speaker's brief
        brief = briefs.get(speaker, {})

        # Speaker's active lorebook
        lorebook_path = os.path.join(dialogue_dir, f"active_lorebook_{speaker}.json")
        lorebook = load_json(lorebook_path) or []

        cache = {
            "dialogue_id": args.dialogue_id,
            "turn_index": i,
            "total_turns": len(turns),
            "speaker": speaker,
            "scene_context": scene_context,
            "scene_anchor": scene_anchor,
            "plan_turn": turn,
            "character_brief": brief,
            "lorebook_entries": lorebook,
            "writing_rules": writing_rules,
            "prose_tail": prose_tail,
        }

        out_path = os.path.join(dialogue_dir, f"turn_context_{i}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        built += 1

    print(f"BUILT: {built} turn context cache(s) for {args.dialogue_id}")


if __name__ == "__main__":
    main()
