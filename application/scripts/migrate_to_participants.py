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

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable, cast


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def migrate_characters(data: dict[str, Any]) -> dict[str, Any] | None:
    if "participants" in data:
        return None  # already migrated
    participants: dict[str, Any] = {}
    for slot in ("charA", "charB"):
        entry_any: Any = data.get(slot)
        if not entry_any:
            continue
        if not isinstance(entry_any, dict):
            continue
        entry: dict[str, Any] = cast(dict[str, Any], entry_any)
        if "id" in entry:
            cid_any: Any = entry["id"]
            cid = cid_any if isinstance(cid_any, str) else str(cid_any)
        else:
            # Raw character without an id yet — derive from name
            name_any: Any = entry.get("name", "")
            name = name_any if isinstance(name_any, str) else ""
            cid = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
            cid = "_".join(s for s in cid.split("_") if s)
        participant_entry: dict[str, Any] = {"id": cid, "name": entry.get("name", cid)}
        participants[cid] = participant_entry
        if entry.get("data_path"):
            participant_entry["data_path"] = entry["data_path"]
        if entry.get("needs_repack"):
            participant_entry["needs_repack"] = True
        if entry.get("raw_path"):
            participant_entry["raw_path"] = entry["raw_path"]

    out: dict[str, Any] = {"participants": participants}
    leading_any: Any = data.get("leading")
    if isinstance(leading_any, dict):
        leading: dict[str, Any] = cast(dict[str, Any], leading_any)
        if leading.get("id"):
            out["leading_id"] = leading["id"]
    return out


def migrate_scenario(data: dict[str, Any]) -> dict[str, Any] | None:
    if "participants" in data:
        return None  # already migrated
    out: dict[str, Any] = {}
    if data.get("dialogue_id"):
        out["dialogue_id"] = data["dialogue_id"]
    if data.get("generated_at"):
        out["generated_at"] = data["generated_at"]

    participants: dict[str, Any] = {}
    chars_block: dict[str, Any] = cast(dict[str, Any], data.get("characters", {}) or {})
    for slot_key in ("char_a", "char_b"):
        meta: dict[str, Any] = cast(dict[str, Any], chars_block.get(slot_key, {}) or {})
        cid_any: Any = meta.get("id")
        if not cid_any or not isinstance(cid_any, str):
            continue
        cid: str = cid_any
        slot_data: dict[str, Any] = cast(dict[str, Any], data.get(slot_key, {}) or {})
        participants[cid] = {
            "name": meta.get("name", cid),
            "scenario": slot_data.get("scenario", ""),
            "openings": slot_data.get("openings", []),
        }
    out["participants"] = participants
    return out


def main() -> None:
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

        migrators: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any] | None]]] = [
            (chars_path, migrate_characters),
            (scen_path, migrate_scenario),
        ]
        for path, migrator in migrators:
            if not os.path.exists(path):
                continue
            data: dict[str, Any] = cast(dict[str, Any], load_json(path))
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
