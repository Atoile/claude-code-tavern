#!/usr/bin/env python3
"""
build_context_cache.py — Builds per-character context cache files.

Writes:
  context_cache.json           — meta: scenario text, leading_id, participant_ids[]
  context_cache_{char_id}.json — per-character: sliced identity/appearance/personality/speech/behavior

The planner reads the meta file + each per-character file it needs. The
validator does NOT read these (uses character_briefs from the plan instead).
Turn agents also don't read these.

Lorebook selection is handled by build_active_lorebook.py (runs every turn).

Skips if context_cache.json already exists AND every source file is older than
the cache. Rebuilds automatically if any source has been edited since.

Usage:
    python application/scripts/build_context_cache.py --dialogue-id <id>
"""

import argparse
import json
import os
import sys

# Overwrite file for additional character fields. Lorebook key patterns in this
# file are consumed by build_active_lorebook.py, not by this script.
OVERWRITE_PATH = "application/scripts/build_context_cache.overwrite.json"

# Field truncation limits — applied to every extracted value to keep the cache
# small enough that subagent read-overhead stays low. Strings over the cap are
# truncated with an ellipsis; lists over the cap are sliced; list string items
# are also individually truncated.
FIELD_STR_MAX = 500
FIELD_LIST_MAX = 5
FIELD_LIST_ITEM_MAX = 250

# Character data fields to extract (SFW baseline)
CHARACTER_FIELDS = {
    "identity": ["full_name", "gender", "occupation", "background_summary"],
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
    if not os.path.exists(OVERWRITE_PATH):
        return
    overwrite = load_json(OVERWRITE_PATH)
    for section, fields in overwrite.get("additional_character_fields", {}).items():
        if section in CHARACTER_FIELDS:
            CHARACTER_FIELDS[section].extend(f for f in fields if f not in CHARACTER_FIELDS[section])
        else:
            CHARACTER_FIELDS[section] = list(fields)


def _truncate_str(s, cap):
    if not isinstance(s, str):
        return s
    if len(s) <= cap:
        return s
    return s[:cap].rstrip() + "…"


def truncate_value(v):
    """Recursively truncate strings and lists to keep the cache compact."""
    if isinstance(v, str):
        return _truncate_str(v, FIELD_STR_MAX)
    if isinstance(v, list):
        truncated = []
        for item in v[:FIELD_LIST_MAX]:
            if isinstance(item, str):
                truncated.append(_truncate_str(item, FIELD_LIST_ITEM_MAX))
            else:
                truncated.append(truncate_value(item))
        return truncated
    if isinstance(v, dict):
        return {k: truncate_value(val) for k, val in v.items()}
    return v


def extract_character(data):
    result = {}
    for section, fields in CHARACTER_FIELDS.items():
        section_data = data.get(section, {})
        result[section] = {f: truncate_value(section_data.get(f)) for f in fields}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dialogue-id", required=True)
    args = parser.parse_args()

    load_overwrite()

    dialogue_dir = os.path.join("infrastructure", "dialogues", args.dialogue_id)
    cache_path = os.path.join(dialogue_dir, "context_cache.json")
    characters_path = os.path.join(dialogue_dir, "characters.json")
    scenario_path = os.path.join(dialogue_dir, "scenario.json")
    goals_path = os.path.join(dialogue_dir, "goals.json")

    if not os.path.exists(characters_path):
        print(f"ERROR: required file not found: {characters_path}", file=sys.stderr)
        sys.exit(1)

    # Either scenario.json (normal mode) or goals.json (narrator mode) must exist
    has_scenario = os.path.exists(scenario_path)
    has_goals = os.path.exists(goals_path)
    if not has_scenario and not has_goals:
        print(f"ERROR: neither scenario.json nor goals.json found in {dialogue_dir}", file=sys.stderr)
        sys.exit(1)

    characters = load_json(characters_path)
    scenario = load_json(scenario_path) if has_scenario else None
    goals = load_json(goals_path) if has_goals else None

    participants = characters.get("participants", {})
    if not participants:
        print("ERROR: characters.json has no participants", file=sys.stderr)
        sys.exit(1)

    # Resolve source data file paths so we can mtime-check them against the cache
    source_files = [characters_path]
    if has_scenario:
        source_files.append(scenario_path)
    if has_goals:
        source_files.append(goals_path)
    for info in participants.values():
        if info.get("data_path") and os.path.exists(info["data_path"]):
            source_files.append(info["data_path"])

    if os.path.exists(cache_path):
        cache_mtime = os.path.getmtime(cache_path)
        stale_sources = [s for s in source_files if os.path.getmtime(s) > cache_mtime]
        if not stale_sources:
            print("OK: context_cache.json is up to date, skipping")
            return
        print(f"REBUILDING: {len(stale_sources)} source file(s) newer than cache: {', '.join(os.path.basename(s) for s in stale_sources)}")

    leading_id = characters.get("leading_id")
    if not leading_id:
        print("ERROR: characters.json has no leading_id", file=sys.stderr)
        sys.exit(1)
    if leading_id not in participants:
        print(f"ERROR: leading_id '{leading_id}' not in participants", file=sys.stderr)
        sys.exit(1)

    # Validate every participant has a data_path on disk
    for cid, info in participants.items():
        if not info.get("data_path"):
            print(f"ERROR: missing data_path for participant: {cid}", file=sys.stderr)
            sys.exit(1)
        if not os.path.exists(info["data_path"]):
            print(f"ERROR: data.json not found: {info['data_path']}", file=sys.stderr)
            sys.exit(1)

    # Load every participant's data.json
    char_data = {cid: load_json(info["data_path"]) for cid, info in participants.items()}

    # Pull scene text from scenario.json (normal mode) or goals.json (narrator mode)
    if scenario:
        scenario_participants = scenario.get("participants", {})
        if leading_id not in scenario_participants:
            print(f"ERROR: leading_id '{leading_id}' not in scenario.json participants", file=sys.stderr)
            sys.exit(1)
        scenario_text = scenario_participants[leading_id].get("scenario", "")
    elif goals:
        scenario_text = goals.get("scene", "")
    else:
        scenario_text = ""

    # Write meta file
    meta = {
        "scenario": scenario_text,
        "leading_id": leading_id,
        "participant_ids": sorted(char_data.keys()),
    }
    write_json(cache_path, meta)

    # Write per-character files
    for cid, data in char_data.items():
        char_cache_path = os.path.join(dialogue_dir, f"context_cache_{cid}.json")
        write_json(char_cache_path, extract_character(data))

    # Clean up any stale per-character files from participants no longer in the scene
    for f in os.listdir(dialogue_dir):
        if f.startswith("context_cache_") and f.endswith(".json"):
            cid_from_file = f[len("context_cache_"):-len(".json")]
            if cid_from_file not in char_data:
                os.remove(os.path.join(dialogue_dir, f))

    print(f"BUILT: context_cache for {args.dialogue_id} (meta + {len(char_data)} character file(s))")


if __name__ == "__main__":
    main()
