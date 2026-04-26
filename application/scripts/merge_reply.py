#!/usr/bin/env python3
"""
merge_reply.py — Assembles the final pending_turns.json from per-turn agent files.

Usage:
    python application/scripts/merge_reply.py --dialogue-id <id> --output-path <path>

Reads:
    infrastructure/dialogues/<id>/reply_plan.json     (plan with turn_order, turns[], turn_state)
    infrastructure/dialogues/<id>/reply_turn_<i>.json (one per entry in plan.turns[], i = 0..N-1)

Writes:
    <output-path>  (final { "turns": [...], "turn_state": ... } for append_turns.py)

Also appends the plan's summaries to reply_history.json (rolling buffer, last 5 rounds).
Verbatim turns are excluded from output (they were already materialized into the chat
by apply_verbatim → expand step). All intermediate files are deleted on success.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, cast

HISTORY_MAX_ROUNDS = 5
HISTORY_MAX_TURNS = 20  # rolling buffer size in flat per-turn format


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    plan_path = os.path.join(dialogue_dir, "reply_plan.json")

    if not os.path.exists(plan_path):
        print(f"ERROR: required file not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    plan_raw: Any = load_json(plan_path)
    plan: dict[str, Any] = cast(dict[str, Any], plan_raw) if isinstance(plan_raw, dict) else {}
    plan_turns_raw: Any = plan.get("turns", [])
    plan_turns: list[dict[str, Any]] = []
    if isinstance(plan_turns_raw, list):
        for t in cast(list[Any], plan_turns_raw):
            if isinstance(t, dict):
                plan_turns.append(cast(dict[str, Any], t))
    if not plan_turns:
        print("ERROR: reply_plan.json has no turns", file=sys.stderr)
        sys.exit(1)

    pending_tbc_raw: Any = plan.get("pending_tbc")  # captured before plan is deleted below
    pending_tbc: dict[str, Any] | None = (
        cast(dict[str, Any], pending_tbc_raw) if isinstance(pending_tbc_raw, dict) else None
    )

    # Verbatim turns (first-turn mode) are already in the chat — exclude from output
    verbatim_speakers: set[Any] = {t["speaker"] for t in plan_turns if t.get("verbatim")}

    # Walk the plan in order, picking up the matching reply_turn_<i>.json for each
    turn_files: list[str] = []
    turns: list[dict[str, Any]] = []
    for i, _plan_turn in enumerate(plan_turns):
        turn_path = os.path.join(dialogue_dir, f"reply_turn_{i}.json")
        if not os.path.exists(turn_path):
            print(f"ERROR: missing turn file: {turn_path}", file=sys.stderr)
            sys.exit(1)
        turn_files.append(turn_path)
        turn_data_raw: Any = load_json(turn_path)
        if not isinstance(turn_data_raw, dict):
            print(f"ERROR: malformed turn file: {turn_path}", file=sys.stderr)
            sys.exit(1)
        turn_data: dict[str, Any] = cast(dict[str, Any], turn_data_raw)
        if turn_data.get("speaker") in verbatim_speakers:
            continue
        turns.append(turn_data)

    output: dict[str, Any] = {"turns": turns}

    turn_state: Any = plan.get("turn_state")
    if turn_state is not None:
        output["turn_state"] = turn_state

    # Pass through goal completion data so append_turns.py can act on it
    if plan.get("dialogue_complete"):
        output["dialogue_complete"] = True
        output["goal_resolution"] = plan.get("goal_resolution")

    write_json(args.output_path, output)

    # Append plan summaries to reply_history.json — flat per-turn format.
    # scene_context lives on the first turn of each round only; subsequent turns in
    # the same round omit the field. This lets rollback pop exactly one history entry
    # when the user removes the single most recent chat turn.
    history_path = os.path.join(dialogue_dir, "reply_history.json")
    history_raw: Any = load_json(history_path) if os.path.exists(history_path) else []
    history: list[dict[str, Any]] = []
    if isinstance(history_raw, list):
        for h in cast(list[Any], history_raw):
            if isinstance(h, dict):
                history.append(cast(dict[str, Any], h))

    scene_context: Any = plan.get("scene_context_summary", "")
    for idx, t in enumerate(plan_turns):
        beats_raw: Any = t.get("beats") or []
        beats: list[Any] = cast(list[Any], beats_raw) if isinstance(beats_raw, list) else []
        summary = "; ".join(str(b) for b in beats if b)
        entry: dict[str, Any] = {
            "speaker": t["speaker"],
            "summary": summary,
        }
        if idx == 0:
            entry["scene_context"] = scene_context
        history.append(entry)

    history = history[-HISTORY_MAX_TURNS:]
    write_json(history_path, history)

    # Clean up intermediate files. reply_plan.json is preserved post-merge for
    # inspection/debugging — the orchestrator deletes it at the start of the
    # NEXT round via _clear_stale_round_artifacts. This keeps the last completed
    # round's plan readable while the chat shows its turns.
    for tf in turn_files:
        os.remove(tf)
    prose_tail_path = os.path.join(dialogue_dir, "prose_tail.json")
    if os.path.exists(prose_tail_path):
        os.remove(prose_tail_path)

    # Clean up per-speaker plan slices (narrator per-character model)
    for f in os.listdir(dialogue_dir):
        if f.startswith("plan_slice_") and f.endswith(".json"):
            os.remove(os.path.join(dialogue_dir, f))
    plan_order_path = os.path.join(dialogue_dir, "plan_turn_order.json")
    if os.path.exists(plan_order_path):
        os.remove(plan_order_path)

    # TBC state propagation:
    # - This round consumed any prior tbc.json (the resumer's turn was planned
    #   first and the other reactors held the freeze). Always delete the old
    #   tbc.json unconditionally.
    # - If the new plan ended on a fresh TBC (pending_tbc set), write a new
    #   tbc.json for next round's planner.
    tbc_path = os.path.join(dialogue_dir, "tbc.json")
    if os.path.exists(tbc_path):
        os.remove(tbc_path)
    if pending_tbc:
        write_json(tbc_path, pending_tbc)
        print(f"OK: merged {len(turns)} turn(s) to {args.output_path} | new TBC pending: {pending_tbc.get('speaker')}")
    else:
        print(f"OK: merged {len(turns)} turn(s) to {args.output_path}")


if __name__ == "__main__":
    main()
