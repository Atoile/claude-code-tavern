#!/usr/bin/env python3
"""
build_context_cache.py — Builds infrastructure/dialogues/{id}/context_cache.json.

Extracts sliced character data and the leading character's scenario text into a
single file so generate_reply agents don't need to read scenario.json or full
data.json files.

Skips if context_cache.json already exists (characters don't change mid-dialogue).

Usage:
    python application/scripts/build_context_cache.py --dialogue-id <id>
"""

import argparse
import json
import os
import sys

# Lorebook key patterns always included (SFW baseline)
BASELINE_LOREBOOK_PATTERNS = ["catchphrase"]

# Overwrite file for additional lorebook key patterns and character fields
OVERWRITE_PATH = "application/scripts/build_context_cache.overwrite.json"

# Character data fields to extract (SFW baseline)
CHARACTER_FIELDS = {
    "identity": ["full_name", "gender"],
    "appearance": ["summary", "height", "build", "typical_clothing"],
    "personality": ["core_traits", "emotional_baseline", "quirks"],
    "speech": ["voice_description", "vocabulary_level", "speech_patterns", "sample_lines"],
    "behavior": ["social_style", "relationship_defaults", "triggers", "stress_behaviors"],
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_overwrite():
    """Load overwrite config, merging additional lorebook patterns and character fields."""
    if not os.path.exists(OVERWRITE_PATH):
        return
    overwrite = load_json(OVERWRITE_PATH)
    # Merge additional lorebook key patterns
    BASELINE_LOREBOOK_PATTERNS.extend(overwrite.get("additional_lorebook_key_patterns", []))
    # Merge additional character fields per section
    for section, fields in overwrite.get("additional_character_fields", {}).items():
        if section in CHARACTER_FIELDS:
            CHARACTER_FIELDS[section].extend(f for f in fields if f not in CHARACTER_FIELDS[section])
        else:
            CHARACTER_FIELDS[section] = list(fields)


def load_lorebook_patterns():
    patterns = list(BASELINE_LOREBOOK_PATTERNS)
    return [p.lower() for p in patterns]


def other_char_match_strings(char_data):
    """Return lowercased strings to match against lorebook keys for the other character."""
    identity = char_data.get("identity", {})
    strings = []
    name = identity.get("name") or identity.get("full_name")
    if name:
        strings.append(name.lower())
    char_id = char_data.get("meta", {}).get("id")
    if char_id:
        strings.append(char_id.lower())
    for alias in identity.get("aliases", []):
        strings.append(alias.lower())
    return strings


def lorebook_key_set(lorebook):
    """Return a flat set of lowercased keys across all lorebook entries."""
    keys = set()
    for entry in lorebook:
        for k in entry.get("keys", []):
            keys.add(k.lower())
    return keys


def select_lorebook(lorebook, other_char_strings, patterns, other_char_keys):
    """Return lorebook entries relevant to this scene."""
    selected = []
    for entry in lorebook:
        entry_keys_lower = [k.lower() for k in entry.get("keys", [])]
        # Match against configured key patterns
        if any(pat in key for pat in patterns for key in entry_keys_lower):
            selected.append(entry)
            continue
        # Match against other character's name/aliases/id
        if any(other in key for other in other_char_strings for key in entry_keys_lower):
            selected.append(entry)
            continue
        # Match against shared topics — keys present in both lorebooks
        if any(key in other_char_keys for key in entry_keys_lower):
            selected.append(entry)
    return [{"keys": e["keys"], "content": e["content"]} for e in selected]


def extract_character(data, other_char_strings, patterns, other_char_keys):
    result = {}
    for section, fields in CHARACTER_FIELDS.items():
        section_data = data.get(section, {})
        result[section] = {f: section_data.get(f) for f in fields}
    result["lorebook"] = select_lorebook(
        data.get("lorebook", []), other_char_strings, patterns, other_char_keys
    )
    return result


def resolve_leading_scenario_key(scenario, leading_id):
    """Return 'char_a' or 'char_b' based on which character matches leading_id."""
    chars = scenario.get("characters", {})
    if chars.get("char_a", {}).get("id") == leading_id:
        return "char_a"
    if chars.get("char_b", {}).get("id") == leading_id:
        return "char_b"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    load_overwrite()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    cache_path = os.path.join(dialogue_dir, "context_cache.json")

    if os.path.exists(cache_path):
        print("OK: context_cache.json already exists, skipping")
        return

    characters_path = os.path.join(dialogue_dir, "characters.json")
    scenario_path = os.path.join(dialogue_dir, "scenario.json")

    for path in (characters_path, scenario_path):
        if not os.path.exists(path):
            print(f"ERROR: required file not found: {path}", file=sys.stderr)
            sys.exit(1)

    characters = load_json(characters_path)
    scenario = load_json(scenario_path)

    leading_id = characters.get("leading", {}).get("id")
    if not leading_id:
        print("ERROR: characters.json has no leading.id", file=sys.stderr)
        sys.exit(1)

    char_a_info = characters.get("charA", {})
    char_b_info = characters.get("charB", {})

    for info in (char_a_info, char_b_info):
        if not info.get("data_path"):
            print(f"ERROR: missing data_path for character: {info.get('id')}", file=sys.stderr)
            sys.exit(1)
        if not os.path.exists(info["data_path"]):
            print(f"ERROR: data.json not found: {info['data_path']}", file=sys.stderr)
            sys.exit(1)

    char_a_data = load_json(char_a_info["data_path"])
    char_b_data = load_json(char_b_info["data_path"])

    patterns = load_lorebook_patterns()

    # Leading scenario text
    scenario_key = resolve_leading_scenario_key(scenario, leading_id)
    if not scenario_key:
        print(f"ERROR: leading_id '{leading_id}' not found in scenario.json characters", file=sys.stderr)
        sys.exit(1)
    scenario_text = scenario[scenario_key]["scenario"]

    # Pre-compute lorebook key sets for shared-topic matching
    char_a_keys = lorebook_key_set(char_a_data.get("lorebook", []))
    char_b_keys = lorebook_key_set(char_b_data.get("lorebook", []))

    # Extract character slices (each sees the other's data for lorebook matching)
    char_a_slice = extract_character(
        char_a_data,
        other_char_strings=other_char_match_strings(char_b_data),
        patterns=patterns,
        other_char_keys=char_b_keys,
    )
    char_b_slice = extract_character(
        char_b_data,
        other_char_strings=other_char_match_strings(char_a_data),
        patterns=patterns,
        other_char_keys=char_a_keys,
    )

    cache = {
        "scenario": scenario_text,
        "characters": {
            char_a_info["id"]: char_a_slice,
            char_b_info["id"]: char_b_slice,
        },
    }

    write_json(cache_path, cache)
    print(f"BUILT: context_cache.json for {args.dialogue_id}")


if __name__ == "__main__":
    main()
