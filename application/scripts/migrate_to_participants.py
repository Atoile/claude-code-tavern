#!/usr/bin/env python3
"""
migrate_to_participants.py — One-shot migration of dialogue files from the
old charA/charB slot schema to the new participants-dict schema.

Run once after the schema cutover, then delete this file.

Usage:
    python application/scripts/migrate_to_participants.py [--dry-run]

Migrates in-place under infrastructure/dialogues/*/:
    characters.json: {charA, charB, leading?, replying?}
        -> {participants: {<id>: {...}}, leading_id?}
    scenario.json:   {characters: {char_a, char_b}, char_a: {...}, char_b: {...}}
        -> {dialogue_id, generated_at, participants: {<id>: {name, scenario, openings}}}

Files already in the new shape are skipped (idempotent).
"""

import argparse
import json
import os
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def migrate_characters(data):
    if "participants" in data:
        return None  # already migrated
    participants = {}
    for slot in ("charA", "charB"):
        entry = data.get(slot)
        if not entry:
            continue
        if "id" in entry:
            cid = entry["id"]
        else:
            # Raw character without an id yet — derive from name
            name = entry.get("name", "")
            cid = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
            cid = "_".join(s for s in cid.split("_") if s)
        participants[cid] = {"id": cid, "name": entry.get("name", cid)}
        if entry.get("data_path"):
            participants[cid]["data_path"] = entry["data_path"]
        if entry.get("needs_repack"):
            participants[cid]["needs_repack"] = True
        if entry.get("raw_path"):
            participants[cid]["raw_path"] = entry["raw_path"]

    out = {"participants": participants}
    leading = data.get("leading")
    if leading and leading.get("id"):
        out["leading_id"] = leading["id"]
    return out


def migrate_scenario(data):
    if "participants" in data:
        return None  # already migrated
    out = {}
    if data.get("dialogue_id"):
        out["dialogue_id"] = data["dialogue_id"]
    if data.get("generated_at"):
        out["generated_at"] = data["generated_at"]

    participants = {}
    chars_block = data.get("characters", {})
    for slot_key in ("char_a", "char_b"):
        meta = chars_block.get(slot_key, {})
        cid = meta.get("id")
        if not cid:
            continue
        slot_data = data.get(slot_key, {}) or {}
        participants[cid] = {
            "name": meta.get("name", cid),
            "scenario": slot_data.get("scenario", ""),
            "openings": slot_data.get("openings", []),
        }
    out["participants"] = participants
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dialogues_dir = os.path.join("infrastructure", "dialogues")
    if not os.path.isdir(dialogues_dir):
        print(f"ERROR: {dialogues_dir} not found", file=sys.stderr)
        sys.exit(1)

    migrated = 0
    skipped = 0
    for entry in sorted(os.listdir(dialogues_dir)):
        ddir = os.path.join(dialogues_dir, entry)
        if not os.path.isdir(ddir):
            continue

        chars_path = os.path.join(ddir, "characters.json")
        scen_path = os.path.join(ddir, "scenario.json")

        for path, migrator in ((chars_path, migrate_characters), (scen_path, migrate_scenario)):
            if not os.path.exists(path):
                continue
            data = load_json(path)
            new_data = migrator(data)
            if new_data is None:
                skipped += 1
                print(f"SKIP {os.path.relpath(path)} (already migrated)")
                continue
            print(f"{'WOULD WRITE' if args.dry_run else 'WRITE'} {os.path.relpath(path)}")
            if not args.dry_run:
                write_json(path, new_data)
                migrated += 1

    print(f"\nDone. {migrated} file(s) migrated, {skipped} skipped.")


if __name__ == "__main__":
    main()
