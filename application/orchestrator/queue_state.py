"""Queue file I/O — atomic reads/writes, FIFO+depends_on picking, status mutations.

The orchestrator is the single writer of `status` fields. Writes are atomic
(tempfile + os.replace) so a crash mid-write never corrupts the file.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
QUEUE_PATH = REPO / "infrastructure" / "queue" / "queue.json"


def read_queue() -> list[dict[str, Any]]:
    if not QUEUE_PATH.exists():
        return []
    text = QUEUE_PATH.read_text(encoding="utf-8")
    if not text.strip():
        return []
    return json.loads(text)


def _write_atomic(items: list[dict[str, Any]]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(QUEUE_PATH.parent), prefix=".queue.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        os.replace(tmp, QUEUE_PATH)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def persist(items: list[dict[str, Any]]) -> None:
    _write_atomic(items)


def pick_next(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """First item with status=pending and every depends_on id done."""
    done_ids = {it["id"] for it in items if it.get("status") == "done"}
    for it in items:
        if it.get("status") != "pending":
            continue
        deps = it.get("depends_on") or []
        if all(dep in done_ids for dep in deps):
            return it
    return None


def gc_done(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop done items. Errors stick for triage."""
    return [it for it in items if it.get("status") != "done"]


def has_processing(items: list[dict[str, Any]]) -> bool:
    return any(it.get("status") == "processing" for it in items)
