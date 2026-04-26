"""Phase 4 — append + optional Phase 4b finalization + condense check.

append_turns.py reads pending_turns.json and writes the turns to full_chat.json
+ recent_chat.json (and turn_state.json if present in the bundle). Its stdout
contains markers (CONDENSE_NEEDED, GOAL_COMPLETED) that the orchestrator parses
to decide what runs after.
"""

from __future__ import annotations

import subprocess
import sys

from ...env import TavernConfig
from ...prompts import REPO


async def run_phase_4(
    dialogue_id: str,
    output_path: str,
    user_prompt: str | None,
    cfg: TavernConfig,
) -> None:
    cmd = [
        sys.executable,
        "application/scripts/append_turns.py",
        "--dialogue-id", dialogue_id,
        "--turns-file", output_path,
    ]
    if user_prompt:
        cmd += ["--user-prompt", user_prompt]
    proc = subprocess.run(cmd, cwd=str(REPO), check=True, capture_output=True, text=True)
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")

    # Phase 4b — turn_finalization.py if overwrite defines it
    if cfg.has_phase_4b:
        subprocess.run(
            [sys.executable, "application/scripts/turn_finalization.py",
             "--dialogue-id", dialogue_id],
            cwd=str(REPO),
            check=True,
        )

    # Inline triggers
    if "CONDENSE_NEEDED" in output:
        from ..condense_memory import run_inline as run_condense_inline
        await run_condense_inline(dialogue_id, cfg)

    if "GOAL_COMPLETED" in output:
        # append_turns.py has already written complete.json + updated goals.json.
        # Just surface the message to the user — orchestrator caller logs it.
        print(f"Dialogue {dialogue_id}: goal completed (see complete.json).")

    # Cleanup intermediates
    subprocess.run(
        [sys.executable, "application/scripts/cleanup_round.py",
         "--dialogue-id", dialogue_id],
        cwd=str(REPO),
        check=True,
    )
