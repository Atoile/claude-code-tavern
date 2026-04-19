#!/usr/bin/env python3
"""
build_active_lorebook.py — Per-turn lorebook selection.

Runs every turn in Phase 0. Reads each participant's full lorebook from their
data.json and writes infrastructure/dialogues/{id}/active_lorebook.json with
entries filtered by four criteria:

1. always: true entries
2. Baseline pattern match (from build_context_cache.overwrite.json —
   "additional_lorebook_key_patterns" + conditional gender-gated patterns)
3. Cross-character name match: entry keys that contain another participant's
   name/id/alias substring (the lore owner has character-specific lore about
   another participant in the scene)
4. Haystack keyword match: any entry key appears as a substring in the
   concatenated recent-prose haystack (prose_tail + last_turn + recent_chat
   tail + user_prompt if provided)

Output — dict-keyed by char_id so reply agents only read their own slice.
Within each character's slice, entries are sorted by priority descending
(ties preserve original lorebook order):

{
  "generated_at": "<iso>",
  "haystack_char_count": <int>,
  "entries_by_char": {
    "<char_id>": [
      {
        "keys": [...],
        "content": "...",
        "priority": <int>,
        "trigger": "always|pattern|cross_char|keyword",
        "matched": [...]
      }
    ]
  }
}

Usage:
    python application/scripts/build_active_lorebook.py --dialogue-id <id> [--user-prompt "<text>"]
"""

import argparse
import datetime
import json
import os
import sys

OVERWRITE_PATH = "application/scripts/build_context_cache.overwrite.json"
RECENT_CHAT_TAIL = 5  # how many last entries of recent_chat.json to add to haystack


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_patterns(scene_genders):
    """Return list of lowercased baseline patterns active for this scene."""
    if not os.path.exists(OVERWRITE_PATH):
        return []
    ov = load_json(OVERWRITE_PATH)
    patterns = list(ov.get("additional_lorebook_key_patterns", []))
    scene_gender_set = {(g or "").lower() for g in scene_genders}
    for rule in ov.get("conditional_lorebook_key_patterns", []):
        required = {g.lower() for g in rule.get("if_any_gender", [])}
        if required & scene_gender_set:
            patterns.extend(rule.get("patterns", []))
    return [p.lower() for p in patterns]


def char_match_strings(char_data):
    """Lowercased name/id/alias strings for a character."""
    identity = char_data.get("identity", {})
    strings = []
    for name_field in ("name", "full_name"):
        v = identity.get(name_field)
        if v:
            strings.append(v.lower())
    char_id = char_data.get("meta", {}).get("id")
    if char_id:
        strings.append(char_id.lower())
    for alias in identity.get("aliases", []) or []:
        strings.append(alias.lower())
    return list({s for s in strings if s})


def build_haystack(dialogue_dir, user_prompt):
    """Concatenate recent-prose sources into a single lowercased haystack."""
    parts = []

    # Include goals.json scene text so scene-relevant lore fires on first round
    goals_path = os.path.join(dialogue_dir, "goals.json")
    if os.path.exists(goals_path):
        goals = load_json(goals_path)
        scene_text = goals.get("scene", "")
        if scene_text:
            parts.append(scene_text)
        for goal in goals.get("goals", []):
            desc = goal.get("description", "")
            if desc:
                parts.append(desc)

    prose_tail_path = os.path.join(dialogue_dir, "prose_tail.json")
    if os.path.exists(prose_tail_path):
        data = load_json(prose_tail_path)
        if isinstance(data, list):
            for entry in data:
                text = entry.get("text") if isinstance(entry, dict) else None
                if text:
                    parts.append(text)
        elif isinstance(data, dict):
            for entry in data.get("turns", []) or []:
                text = entry.get("text") if isinstance(entry, dict) else None
                if text:
                    parts.append(text)

    last_turn_path = os.path.join(dialogue_dir, "last_turn.json")
    if os.path.exists(last_turn_path):
        data = load_json(last_turn_path)
        text = data.get("text") if isinstance(data, dict) else None
        if text:
            parts.append(text)

    recent_chat_path = os.path.join(dialogue_dir, "recent_chat.json")
    if os.path.exists(recent_chat_path):
        data = load_json(recent_chat_path)
        if isinstance(data, list):
            for entry in data[-RECENT_CHAT_TAIL:]:
                text = entry.get("text") if isinstance(entry, dict) else None
                if text:
                    parts.append(text)

    if user_prompt:
        parts.append(user_prompt)

    return "\n".join(parts).lower()


def select_entries(lorebook, other_name_strings, patterns, haystack):
    """Apply the four criteria to one character's lorebook and return shaped entries."""
    results = []
    for entry in lorebook:
        keys = entry.get("keys", []) or []
        keys_lower = [k.lower() for k in keys]
        priority = entry.get("priority", 0) or 0

        if entry.get("always"):
            results.append({
                "keys": keys,
                "content": entry.get("content", ""),
                "priority": priority,
                "trigger": "always",
                "matched": [],
            })
            continue

        pattern_hits = [p for p in patterns for k in keys_lower if p in k]
        if pattern_hits:
            results.append({
                "keys": keys,
                "content": entry.get("content", ""),
                "priority": priority,
                "trigger": "pattern",
                "matched": sorted(set(pattern_hits)),
            })
            continue

        cross_hits = [n for n in other_name_strings for k in keys_lower if n in k]
        if cross_hits:
            results.append({
                "keys": keys,
                "content": entry.get("content", ""),
                "priority": priority,
                "trigger": "cross_char",
                "matched": sorted(set(cross_hits)),
            })
            continue

        keyword_hits = [k for k in keys_lower if k and k in haystack]
        if keyword_hits:
            results.append({
                "keys": keys,
                "content": entry.get("content", ""),
                "priority": priority,
                "trigger": "keyword",
                "matched": sorted(set(keyword_hits)),
            })

    results.sort(key=lambda e: e["priority"], reverse=True)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    parser.add_argument("--user-prompt", default=None)
    args = parser.parse_args()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    characters_path = os.path.join(dialogue_dir, "characters.json")
    output_path = os.path.join(dialogue_dir, "active_lorebook.json")

    if not os.path.exists(characters_path):
        print(f"ERROR: characters.json not found: {characters_path}", file=sys.stderr)
        sys.exit(1)

    characters = load_json(characters_path)
    participants = characters.get("participants", {})
    if not participants:
        print("ERROR: characters.json has no participants", file=sys.stderr)
        sys.exit(1)

    char_data = {}
    for cid, info in participants.items():
        data_path = info.get("data_path")
        if not data_path or not os.path.exists(data_path):
            print(f"ERROR: data.json not found for {cid}: {data_path}", file=sys.stderr)
            sys.exit(1)
        char_data[cid] = load_json(data_path)

    scene_genders = [d.get("identity", {}).get("gender") for d in char_data.values()]
    patterns = load_patterns(scene_genders)

    char_strings = {cid: char_match_strings(d) for cid, d in char_data.items()}

    haystack = build_haystack(dialogue_dir, args.user_prompt)

    entries_by_char = {}
    for cid, data in char_data.items():
        other_strings = []
        for other_cid, strings in char_strings.items():
            if other_cid == cid:
                continue
            other_strings.extend(strings)
        other_strings = list({s for s in other_strings if s})

        lorebook = data.get("lorebook", []) or []
        entries_by_char[cid] = select_entries(lorebook, other_strings, patterns, haystack)

    output = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "haystack_char_count": len(haystack),
        "entries_by_char": entries_by_char,
    }
    write_json(output_path, output)

    # Write per-character lorebook files for turn context caching
    for cid, entries in entries_by_char.items():
        char_path = os.path.join(dialogue_dir, f"active_lorebook_{cid}.json")
        write_json(char_path, entries)

    total = sum(len(v) for v in entries_by_char.values())
    by_trigger = {}
    for entries in entries_by_char.values():
        for e in entries:
            by_trigger[e["trigger"]] = by_trigger.get(e["trigger"], 0) + 1
    trigger_summary = ", ".join(f"{k}={v}" for k, v in sorted(by_trigger.items()))
    print(f"OK: active_lorebook.json — {total} entries ({trigger_summary})")


if __name__ == "__main__":
    main()
