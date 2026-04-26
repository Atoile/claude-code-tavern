#!/usr/bin/env python3
"""
enqueue.py — Appends task(s) to infrastructure/queue/queue.json.

Portable helper that encapsulates the queue-append business logic as a CLI
script so both the Svelte prototype and the Godot port can share the same
contract. Business logic should live here, not in UI code.

Usage:
    python application/scripts/enqueue.py --task-file <path>
    python application/scripts/enqueue.py --task-json '<json-string>'
    cat task.json | python application/scripts/enqueue.py --stdin

The input is either a single task object or an array of task objects. Any
task missing an `id` gets a fresh UUID. Any task missing `status` gets
`"pending"`. Any task missing `parallel` gets `false`. Any task missing
`depends_on` gets an empty array. Other fields are passed through untouched.

The queue file is read, new tasks are appended in order, and the file is
written back atomically (temp file + rename) so concurrent readers never see
a partial write.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from typing import Any, cast

QUEUE_PATH = os.path.join("infrastructure", "queue", "queue.json")


def load_queue() -> list[Any]:
    if not os.path.exists(QUEUE_PATH):
        return []
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        data: Any = json.load(f)
    if not isinstance(data, list):
        print(f"ERROR: {QUEUE_PATH} is not a JSON array", file=sys.stderr)
        sys.exit(1)
    return cast(list[Any], data)


def write_queue_atomic(data: list[Any]) -> None:
    queue_dir = os.path.dirname(QUEUE_PATH)
    os.makedirs(queue_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=queue_dir, prefix=".queue.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, QUEUE_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def normalize_task(task: Any) -> dict[str, Any]:
    if not isinstance(task, dict):
        raise ValueError(f"task must be a JSON object, got {type(task).__name__}")
    t: dict[str, Any] = cast(dict[str, Any], task)
    if "type" not in t:
        raise ValueError("task missing required field: type")
    t.setdefault("id", str(uuid.uuid4()))
    t.setdefault("status", "pending")
    t.setdefault("parallel", False)
    t.setdefault("depends_on", [])
    return t


def load_input(args: argparse.Namespace) -> list[Any]:
    if args.stdin:
        raw = sys.stdin.read()
    elif args.task_json is not None:
        raw = args.task_json
    elif args.task_file is not None:
        with open(args.task_file, "r", encoding="utf-8") as f:
            raw = f.read()
    else:
        print("ERROR: provide --task-file, --task-json, or --stdin", file=sys.stderr)
        sys.exit(1)
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    if isinstance(data, dict):
        return [cast(dict[str, Any], data)]
    if isinstance(data, list):
        return cast(list[Any], data)
    print(f"ERROR: input must be an object or array, got {type(data).__name__}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--task-file", help="Path to JSON file with task object or array")
    group.add_argument("--task-json", help="JSON string containing task object or array")
    group.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    args = parser.parse_args()

    new_tasks_raw = load_input(args)
    try:
        new_tasks: list[dict[str, Any]] = []
        for t in new_tasks_raw:
            if not isinstance(t, dict):
                raise ValueError(f"task must be a JSON object, got {type(t).__name__}")
            new_tasks.append(normalize_task(dict(cast(dict[str, Any], t))))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    queue = load_queue()
    queue.extend(new_tasks)
    write_queue_atomic(queue)

    ids = [str(t["id"]) for t in new_tasks]
    print(f"OK: appended {len(new_tasks)} task(s) to {QUEUE_PATH} | ids: {', '.join(ids)}")


if __name__ == "__main__":
    main()
