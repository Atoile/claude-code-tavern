#!/usr/bin/env python3
"""
check_beat_sizing.py — Deterministic beat/tone/weight-cap sizing check for reply_plan.json.

Usage:
    python "application/scripts/check_beat_sizing.py" --dialogue-id <id>
    python "application/scripts/check_beat_sizing.py" --plan-path <path>

Writes:
    infrastructure/dialogues/<id>/beat_sizing.json   (when --dialogue-id is used)

Prints:
    Human-readable summary to stdout (PASS / FAIL with violation count).

Mode-aware: reads plan["mode"] and applies the correct caps per mode.

Standard mode caps:
    - Beat word cap: 25 words
    - Tone word cap: 40 words
    - Beat count by weight: reaction[1,2], action[2,3], inflection[3,4], climax[4,6]

Narrator mode caps (plan["mode"] == "narrator"):
    - Beat word cap: 120 words (both speech and narration beats)
    - Tone word cap: 40 words
    - Beat count by type: speech[1,3], narration[1,3]
    - Weight field is not used — beat count checked against turn["type"] instead

Word count rule: len(text.split()) — split on any whitespace run. Spaced em-dashes
count as their own token; contractions ("she's") count as one word. Punctuation
attached to a word is part of that word token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, cast

# Standard mode
BEAT_WORD_CAP_STANDARD = 25
TONE_WORD_CAP = 40
WEIGHT_CAPS: dict[str, list[int]] = {
    "reaction":   [1, 2],
    "action":     [2, 3],
    "inflection": [3, 4],
    "climax":     [4, 6],
}

# Narrator mode
BEAT_WORD_CAP_NARRATOR = 120
TYPE_CAPS_NARRATOR: dict[str, list[int]] = {
    "speech":    [1, 3],
    "narration": [1, 3],
}


def count_words(text: Any) -> int:
    if not isinstance(text, str):
        return 0
    return len(text.split())


def check_plan(plan: dict[str, Any]) -> dict[str, Any]:
    narrator_mode = plan.get("mode") == "narrator"
    beat_word_cap = BEAT_WORD_CAP_NARRATOR if narrator_mode else BEAT_WORD_CAP_STANDARD

    turns_report: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []

    for i, turn_any in enumerate(cast(list[Any], plan.get("turns", []) or [])):
        turn: dict[str, Any] = cast(dict[str, Any], turn_any) if isinstance(turn_any, dict) else {}
        speaker = turn.get("speaker", "?")
        beats: list[Any] = cast(list[Any], turn.get("beats", []) or [])
        tone = turn.get("tone", "")
        beat_count = len(beats)
        beat_count_ok = True

        weight: Any
        weight_cap: list[int] | None
        if narrator_mode:
            turn_type_any: Any = turn.get("type", "?")
            turn_type = turn_type_any if isinstance(turn_type_any, str) else "?"
            type_cap = TYPE_CAPS_NARRATOR.get(turn_type)
            weight = turn_type  # use type as label for reporting
            weight_cap = type_cap
            if type_cap is not None:
                lo, hi = type_cap
                beat_count_ok = lo <= beat_count <= hi
                if not beat_count_ok:
                    violations.append({
                        "kind": "beat_count",
                        "turn_index": i,
                        "speaker": speaker,
                        "type": turn_type,
                        "beat_count": beat_count,
                        "cap": type_cap,
                        "detail": (
                            f"Turn {i} ({speaker}) type '{turn_type}' requires "
                            f"{lo}-{hi} beats but has {beat_count}."
                        ),
                    })
        else:
            weight_any: Any = turn.get("weight", "?")
            weight = weight_any if isinstance(weight_any, str) else "?"
            weight_cap = WEIGHT_CAPS.get(weight) if isinstance(weight, str) else None
            if weight_cap is not None:
                lo, hi = weight_cap
                beat_count_ok = lo <= beat_count <= hi
                if not beat_count_ok:
                    violations.append({
                        "kind": "beat_count",
                        "turn_index": i,
                        "speaker": speaker,
                        "weight": weight,
                        "beat_count": beat_count,
                        "cap": weight_cap,
                        "detail": (
                            f"Turn {i} ({speaker}) weight '{weight}' requires "
                            f"{lo}-{hi} beats but has {beat_count}."
                        ),
                    })

        beats_report: list[dict[str, Any]] = []
        for bi, beat in enumerate(beats, start=1):
            wc = count_words(beat)
            over = wc > beat_word_cap
            beats_report.append({
                "index": bi,
                "word_count": wc,
                "over_cap": over,
                "text": beat,
            })
            if over:
                violations.append({
                    "kind": "beat_oversized",
                    "turn_index": i,
                    "speaker": speaker,
                    "beat_index": bi,
                    "word_count": wc,
                    "cap": beat_word_cap,
                    "excess": wc - beat_word_cap,
                    "text": beat,
                    "detail": (
                        f"Turn {i} ({speaker}) beat {bi} is {wc} words "
                        f"(cap {beat_word_cap}, over by {wc - beat_word_cap})."
                    ),
                })

        tone_wc = count_words(tone)
        tone_over = tone_wc > TONE_WORD_CAP
        if tone_over:
            violations.append({
                "kind": "tone_oversized",
                "turn_index": i,
                "speaker": speaker,
                "word_count": tone_wc,
                "cap": TONE_WORD_CAP,
                "excess": tone_wc - TONE_WORD_CAP,
                "text": tone,
                "detail": (
                    f"Turn {i} ({speaker}) tone is {tone_wc} words "
                    f"(cap {TONE_WORD_CAP}, over by {tone_wc - TONE_WORD_CAP})."
                ),
            })

        turns_report.append({
            "index": i,
            "speaker": speaker,
            "weight": weight,
            "weight_cap": weight_cap,
            "beat_count": beat_count,
            "beat_count_ok": beat_count_ok,
            "beats": beats_report,
            "tone_word_count": tone_wc,
            "tone_over_cap": tone_over,
            "tone_text": tone,
        })

    summary: dict[str, Any] = {
        "mode": "narrator" if narrator_mode else "standard",
        "total_turns": len(turns_report),
        "beat_oversized_count": sum(1 for v in violations if v["kind"] == "beat_oversized"),
        "tone_oversized_count": sum(1 for v in violations if v["kind"] == "tone_oversized"),
        "beat_count_violations": sum(1 for v in violations if v["kind"] == "beat_count"),
        "pass": len(violations) == 0,
    }

    rules: dict[str, Any] = {
        "mode": "narrator" if narrator_mode else "standard",
        "beat_word_cap": beat_word_cap,
        "tone_word_cap": TONE_WORD_CAP,
        "word_count_method": "whitespace-split (len(text.split()))",
    }
    if narrator_mode:
        rules["type_caps"] = TYPE_CAPS_NARRATOR
    else:
        rules["weight_caps"] = WEIGHT_CAPS

    return {
        "rules": rules,
        "turns": turns_report,
        "summary": summary,
        "violations": violations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dialogue-id")
    group.add_argument("--plan-path")
    parser.add_argument("--no-write", action="store_true",
                        help="Skip writing beat_sizing.json (print JSON report to stdout instead of summary).")
    args = parser.parse_args()

    if args.dialogue_id:
        dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
        plan_path = os.path.join(dialogue_dir, "reply_plan.json")
        output_path = os.path.join(dialogue_dir, "beat_sizing.json")
    else:
        plan_path = args.plan_path
        dialogue_dir = os.path.dirname(plan_path)
        output_path = os.path.join(dialogue_dir, "beat_sizing.json")

    if not os.path.exists(plan_path):
        print(f"ERROR: plan not found at {plan_path}", file=sys.stderr)
        sys.exit(2)

    with open(plan_path, "r", encoding="utf-8") as f:
        plan: dict[str, Any] = cast(dict[str, Any], json.load(f))

    report = check_plan(plan)

    if args.no_write:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    s: dict[str, Any] = cast(dict[str, Any], report["summary"])
    status = "PASS" if s["pass"] else "FAIL"
    print(
        f"{status} [{s['mode']}]: {output_path} | "
        f"turns={s['total_turns']} "
        f"beat_oversized={s['beat_oversized_count']} "
        f"tone_oversized={s['tone_oversized_count']} "
        f"beat_count_violations={s['beat_count_violations']}"
    )

    if not s["pass"]:
        for v in cast(list[dict[str, Any]], report["violations"]):
            print(f"  - {v['detail']}")


if __name__ == "__main__":
    main()
