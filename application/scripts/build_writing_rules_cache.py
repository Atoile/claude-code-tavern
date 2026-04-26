#!/usr/bin/env python3
"""
build_writing_rules_cache.py — Rebuilds domain/dialogue/writing_rules_cache.md
by merging writing_rules.md and writing_rules.overwrite.md (if present).

Skips rebuild if cache is newer than all source files.

Usage:
    python application/scripts/build_writing_rules_cache.py
"""

from __future__ import annotations

import os
import sys

SOURCES = [
    "domain/dialogue/writing_rules.md",
    "domain/dialogue/writing_rules.overwrite.md",
]
CACHE = "domain/dialogue/writing_rules_cache.md"


def main() -> None:
    existing_sources = [s for s in SOURCES if os.path.exists(s)]
    if not existing_sources:
        print("ERROR: no writing_rules source files found", file=sys.stderr)
        sys.exit(1)

    newest_source = max(os.path.getmtime(f) for f in existing_sources)
    cache_mtime = os.path.getmtime(CACHE) if os.path.exists(CACHE) else 0

    if cache_mtime >= newest_source:
        print("OK: writing_rules_cache.md is up to date")
        return

    parts: list[str] = []
    for path in SOURCES:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        # Strip frontmatter (--- ... ---) from individual files
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3:].strip()
        parts.append(content)

    merged = "\n\n---\n\n".join(parts)

    with open(CACHE, "w", encoding="utf-8") as f:
        f.write("# Writing Rules (cached)\n\n")
        f.write(merged)
        f.write("\n")

    print(f"REBUILT: writing_rules_cache.md ({len(existing_sources)} source(s) merged)")


if __name__ == "__main__":
    main()
