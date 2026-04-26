"""build_character_briefs.py — Pre-build character_briefs sidecar.

Distills the per-character voice/identity slice from each
infrastructure/dialogues/{dialogue_id}/context_cache_{char_id}.json into a
single character_briefs.json file.

Replaces the wasteful pattern where the planner agent copy-pasted these
fields into reply_plan.json on every round at output-token cost. The
orchestrator does the same distillation in pure Python for free.

Output schema:
{
  "<char_id>": {
    "name": str,
    "gender": str | null,
    "height": str | null,
    "build": str | null,
    "appearance_summary": str,
    "core_traits": list[str],
    "emotional_baseline": str | null,
    "quirks": list[str],
    "voice_description": str | null,
    "speech_patterns": list[str],
    "vocabulary_level": str | null
  }
}

Idempotent — safe to run every round in Phase 0.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APPEARANCE_SUMMARY_MAX_WORDS = 100


def _truncate_words(s: str | None, n: int) -> str | None:
    if not s:
        return s
    words = s.split()
    if len(words) <= n:
        return s
    return " ".join(words[:n]) + "..."


def _brief_for(char_data: dict, fallback_name: str) -> dict:
    identity = char_data.get("identity", {}) or {}
    appearance = char_data.get("appearance", {}) or {}
    personality = char_data.get("personality", {}) or {}
    speech = char_data.get("speech", {}) or {}
    return {
        "name": identity.get("full_name") or fallback_name,
        "gender": identity.get("gender"),
        "height": appearance.get("height"),
        "build": appearance.get("build"),
        "appearance_summary": _truncate_words(
            appearance.get("summary"), APPEARANCE_SUMMARY_MAX_WORDS
        ) or "",
        "core_traits": list(personality.get("core_traits") or []),
        "emotional_baseline": personality.get("emotional_baseline"),
        "quirks": list(personality.get("quirks") or []),
        "voice_description": speech.get("voice_description"),
        "speech_patterns": list(speech.get("speech_patterns") or []),
        "vocabulary_level": speech.get("vocabulary_level"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build character_briefs.json from context caches")
    ap.add_argument("--dialogue-id", required=True)
    args = ap.parse_args()

    dlg_dir = REPO / "infrastructure" / "dialogues" / args.dialogue_id
    if not dlg_dir.exists():
        print(f"ERROR: dialogue dir not found: {dlg_dir}")
        return 1

    meta_path = dlg_dir / "context_cache.json"
    if not meta_path.exists():
        print(f"ERROR: context_cache.json missing — run build_context_cache.py first")
        return 1

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    participant_ids = meta.get("participant_ids") or []
    if not participant_ids:
        print("ERROR: context_cache.json has no participant_ids")
        return 1

    briefs: dict[str, dict] = {}
    missing: list[str] = []
    for char_id in participant_ids:
        cache_path = dlg_dir / f"context_cache_{char_id}.json"
        if not cache_path.exists():
            missing.append(char_id)
            continue
        char_data = json.loads(cache_path.read_text(encoding="utf-8"))
        briefs[char_id] = _brief_for(char_data, fallback_name=char_id)

    if missing:
        print(f"ERROR: missing per-character caches for: {', '.join(missing)}")
        return 1

    out_path = dlg_dir / "character_briefs.json"
    out_path.write_text(json.dumps(briefs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK: character_briefs.json - {len(briefs)} brief(s) written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
