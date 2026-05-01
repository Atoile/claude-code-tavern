"""Tavern queue runner — Python orchestrator using claude-agent-sdk.

Replaces the interactive "run queue" verbal command. Reads queue.json,
dispatches tasks via stateless Agent SDK spawns, persists status mutations
atomically.

Usage (run from repo root):
  python -m application.orchestrator.run_queue            # drain all eligible
  python -m application.orchestrator.run_queue --once     # one task and exit
  python -m application.orchestrator.run_queue --watch    # poll forever
  python -m application.orchestrator.run_queue --quiet    # suppress info logs

Crash-safe: status=processing is persisted before each spawn. A processing item
on a fresh start signals a prior crash — orchestrator logs and skips, leaving
it for manual triage.
"""

from __future__ import annotations

# Bootstrap: support both invocation styles
#   python -m application.orchestrator.run_queue
#   python application/orchestrator/run_queue.py
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import asyncio
import sys
import time
import traceback
from typing import Any

from application.orchestrator.env import TavernConfig, load_config
from application.orchestrator.pipelines import dispatch
from application.orchestrator.queue_state import gc_done, persist, pick_next, read_queue


def _log(quiet: bool, msg: str) -> None:
    if not quiet:
        print(msg, flush=True)


async def _process_one(
    items: list[dict[str, Any]], cfg: TavernConfig, quiet: bool, start_from: str | None = None
) -> bool:
    """Pick + run + persist for one queue item. Returns True if work was done."""
    item = pick_next(items)
    if item is None:
        return False

    item["status"] = "processing"
    persist(items)
    _log(quiet, f"[{item['type']}] {item.get('id')} → processing")

    try:
        await dispatch(item, cfg, start_from=start_from)
    except (KeyboardInterrupt, asyncio.CancelledError):
        # User hit Ctrl+C (or asyncio cancelled the task tree). Mark the item
        # as interrupted so the next run can detect it cleanly instead of
        # leaving it stuck as 'processing' (which would look like a hard crash).
        item["status"] = "interrupted"
        item["error"] = "KeyboardInterrupt: user-requested abort"
        persist(items)
        _log(quiet, f"[{item['type']}] {item.get('id')} → interrupted")
        raise
    except Exception as e:
        item["status"] = "error"
        item["error"] = f"{type(e).__name__}: {e}"
        persist(items)
        traceback.print_exc()
        raise

    item["status"] = "done"
    persist(items)
    _log(quiet, f"[{item['type']}] {item.get('id')} → done")
    return True


async def _drain(cfg: TavernConfig, quiet: bool, once: bool, start_from: str | None = None) -> int:
    items = read_queue()

    # Recovery check: 'processing' means a prior hard crash; 'interrupted'
    # means a clean Ctrl+C. Both leave dialogue files in an unknown partial
    # state, so neither is auto-resumed — user flips back to 'pending' to retry.
    stuck = [it for it in items if it.get("status") in ("processing", "interrupted")]
    if stuck:
        for it in stuck:
            kind = it.get("status")
            tag = "INTERRUPTED" if kind == "interrupted" else "STUCK"
            _log(quiet, f"WARNING [{tag}]: item {it.get('id', '<no-id>')} ({it.get('type', '?')})")
        _log(quiet, "         Manual triage required — flip status to 'pending' to retry.")
        return 2

    processed_any = False
    try:
        while True:
            # Re-read queue from disk every iteration so externally-appended
            # tasks (frontend, enqueue.py) get picked up mid-drain.
            items = read_queue()
            try:
                did_work = await _process_one(items, cfg, quiet, start_from=start_from)
                start_from = None  # only applies to the first task
            except (KeyboardInterrupt, asyncio.CancelledError):
                _log(quiet, "Aborted by user (Ctrl+C). Item marked 'interrupted'.")
                return 130  # conventional Ctrl+C exit code
            except Exception:
                return 1
            if not did_work:
                break
            processed_any = True
            if once:
                break
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Ctrl+C between items (no item in flight) — exit cleanly.
        _log(quiet, "Aborted by user (Ctrl+C). No item in flight.")
        return 130

    # End-of-drain garbage collection of done items.
    items = read_queue()
    cleaned = gc_done(items)
    if len(cleaned) != len(items):
        persist(cleaned)
        _log(quiet, f"GC: dropped {len(items) - len(cleaned)} done item(s).")

    if not processed_any:
        _log(quiet, "Queue empty — nothing to do.")
    return 0


async def _watch_loop(cfg: TavernConfig, quiet: bool, interval: float) -> int:
    """Poll-mode driver. Drains the queue, sleeps, repeats."""
    while True:
        rc = await _drain(cfg, quiet=quiet, once=False, start_from=None)
        if rc not in (0, 2):
            return rc
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tavern queue orchestrator (Agent SDK)")
    ap.add_argument("--once", action="store_true", help="Process one task and exit.")
    ap.add_argument("--watch", action="store_true", help="Poll queue.json forever.")
    ap.add_argument("--interval", type=float, default=2.0, help="Poll interval in seconds (--watch).")
    ap.add_argument("--quiet", action="store_true", help="Suppress info logs.")
    ap.add_argument(
        "--start-from",
        metavar="PHASE",
        default=None,
        help=(
            "Skip earlier phases of the first eligible task and resume from PHASE. "
            "Valid for generate_reply: phase0 phase0b phase1 phase1b phase2 phase3 phase4. "
            "Example: --start-from phase1b  (re-validate an existing reply_plan.json)"
        ),
    )
    args = ap.parse_args(argv)

    cfg = load_config()
    if not args.quiet:
        print(
            f"Tavern orchestrator: mode={cfg.mode} chat={cfg.chat_mode} "
            f"planner={cfg.planner} narrator_voice={cfg.narrator_voice} "
            f"phase_3b={cfg.has_phase_3b} phase_4b={cfg.has_phase_4b}",
            flush=True,
        )

    try:
        if args.watch:
            return asyncio.run(_watch_loop(cfg, args.quiet, args.interval))
        return asyncio.run(_drain(cfg, quiet=args.quiet, once=args.once, start_from=args.start_from))
    except KeyboardInterrupt:
        # Top-level catch — _drain marks the in-flight item before re-raising,
        # so by the time we land here the queue file is consistent.
        if not args.quiet:
            print("\nAborted.", flush=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
