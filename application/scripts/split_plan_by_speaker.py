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

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, cast


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    parser.add_argument("--narrator-voice", default="neutral")
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    plan_path = os.path.join(dialogue_dir, "reply_plan.json")

    if not os.path.exists(plan_path):
        print(f"ERROR: reply_plan.json not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    plan_raw: Any = load_json(plan_path)
    plan: dict[str, Any] = cast(dict[str, Any], plan_raw) if isinstance(plan_raw, dict) else {}
    turns_raw: Any = plan.get("turns", [])
    turns: list[Any] = cast(list[Any], turns_raw) if isinstance(turns_raw, list) else []
    turn_order: Any = plan.get("turn_order", [])

    # Briefs now live in a sidecar file built by build_character_briefs.py.
    # Fall back to plan.character_briefs if the sidecar is missing.
    briefs_path = os.path.join(dialogue_dir, "character_briefs.json")
    briefs: dict[str, Any]
    if os.path.exists(briefs_path):
        briefs_raw: Any = load_json(briefs_path) or {}
        briefs = cast(dict[str, Any], briefs_raw) if isinstance(briefs_raw, dict) else {}
    else:
        plan_briefs: Any = plan.get("character_briefs", {})
        briefs = cast(dict[str, Any], plan_briefs) if isinstance(plan_briefs, dict) else {}

    scene_ctx: Any = plan.get("scene_context_summary", "")
    protagonist: Any = plan.get("round_protagonist", "")
    scene_anchor_raw: Any = plan.get("scene_anchor") or {}
    scene_anchor: dict[str, Any] = (
        cast(dict[str, Any], scene_anchor_raw) if isinstance(scene_anchor_raw, dict) else {}
    )

    # Group turns by speaker
    speakers: dict[str, dict[str, list[Any]]] = {}
    for i, turn in enumerate(turns):
        if not isinstance(turn, dict):
            continue
        turn_d: dict[str, Any] = cast(dict[str, Any], turn)
        speaker_val: Any = turn_d.get("speaker", "")
        speaker = speaker_val if isinstance(speaker_val, str) else ""
        if speaker not in speakers:
            speakers[speaker] = {"indices": [], "turns": []}
        speakers[speaker]["indices"].append(i)
        speakers[speaker]["turns"].append(turn_d)

    # Write per-speaker slice files
    written: list[str] = []
    for speaker, data in speakers.items():
        slice_data: dict[str, Any] = {
            "speaker": speaker,
            "turn_indices": data["indices"],
            "turns": data["turns"],
            "brief": briefs.get(speaker) if speaker != "_narrator" else None,
            "scene_context_summary": scene_ctx,
            "scene_anchor": scene_anchor,
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
