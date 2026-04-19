#!/usr/bin/env python3
"""
check_beat_sizing.py — Deterministic beat/tone/weight-cap sizing check for reply_plan.json.

Usage:
    python application/scripts/check_beat_sizing.py --dialogue-id <id>
    python application/scripts/check_beat_sizing.py --plan-path <path>

Writes:
    infrastructure/dialogues/<id>/beat_sizing.json   (when --dialogue-id is used)

Prints:
    Human-readable summary to stdout (PASS / FAIL with violation count).

The validator agent invokes this tool instead of counting words by eye — whitespace-
split word counting is deterministic, so the same unchanged plan always produces the
same counts. No more phantom violations across validation passes.

Rules enforced:
    - Each beat string must be <= 25 words (whitespace-split count).
    - Each tone string must be <= 40 words.
    - len(beats) must fall within the weight's [min, max] cap:
        reaction  [1, 2]
        action    [2, 3]
        inflection[3, 4]
        climax    [4, 6]

Word count rule: len(text.split()) — split on any whitespace run. Spaced em-dashes
count as their own token; contractions ("she's") count as one word. Punctuation
attached to a word is part of that word token.
"""

import argparse
import json
import os
import sys

BEAT_WORD_CAP = 25
TONE_WORD_CAP = 40
WEIGHT_CAPS = {
    "reaction":   [1, 2],
    "action":     [2, 3],
    "inflection": [3, 4],
    "climax":     [4, 6],
}


def count_words(text):
    if not isinstance(text, str):
        return 0
    return len(text.split())


def check_plan(plan):
    turns_report = []
    violations = []

    for i, turn in enumerate(plan.get("turns", [])):
        speaker = turn.get("speaker", "?")
        weight = turn.get("weight", "?")
        beats = turn.get("beats", [])
        tone = turn.get("tone", "")

        weight_cap = WEIGHT_CAPS.get(weight)
        beat_count = len(beats)
        beat_count_ok = True
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
                    "detail": f"Turn {i} ({speaker}) weight '{weight}' requires {lo}-{hi} beats but has {beat_count}.",
                })

        beats_report = []
        for bi, beat in enumerate(beats, start=1):
            wc = count_words(beat)
            over = wc > BEAT_WORD_CAP
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
                    "cap": BEAT_WORD_CAP,
                    "excess": wc - BEAT_WORD_CAP,
                    "text": beat,
                    "detail": f"Turn {i} ({speaker}) beat {bi} is {wc} words (cap {BEAT_WORD_CAP}, over by {wc - BEAT_WORD_CAP}).",
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
                "detail": f"Turn {i} ({speaker}) tone is {tone_wc} words (cap {TONE_WORD_CAP}, over by {tone_wc - TONE_WORD_CAP}).",
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

    summary = {
        "total_turns": len(turns_report),
        "beat_oversized_count": sum(1 for v in violations if v["kind"] == "beat_oversized"),
        "tone_oversized_count": sum(1 for v in violations if v["kind"] == "tone_oversized"),
        "beat_count_violations": sum(1 for v in violations if v["kind"] == "beat_count"),
        "pass": len(violations) == 0,
    }

    return {
        "rules": {
            "beat_word_cap": BEAT_WORD_CAP,
            "tone_word_cap": TONE_WORD_CAP,
            "weight_caps": WEIGHT_CAPS,
            "word_count_method": "whitespace-split (len(text.split()))",
        },
        "turns": turns_report,
        "summary": summary,
        "violations": violations,
    }


def main():
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
        plan = json.load(f)

    report = check_plan(plan)

    if args.no_write:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    s = report["summary"]
    status = "PASS" if s["pass"] else "FAIL"
    print(
        f"{status}: {output_path} | "
        f"turns={s['total_turns']} "
        f"beat_oversized={s['beat_oversized_count']} "
        f"tone_oversized={s['tone_oversized_count']} "
        f"beat_count_violations={s['beat_count_violations']}"
    )

    if not s["pass"]:
        for v in report["violations"]:
            print(f"  - {v['detail']}")


if __name__ == "__main__":
    main()
