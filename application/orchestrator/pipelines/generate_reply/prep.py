"""Phase 0 — run five prep scripts in order via subprocess.

All scripts are idempotent. check=True so a crash surfaces immediately.
"""

from __future__ import annotations

import subprocess
import sys

from ...prompts import REPO


def run_phase_0(dialogue_id: str, user_prompt: str | None) -> None:
    py = sys.executable

    # Order matters: lorebook reads prose_tail + last_turn outputs.
    # build_character_briefs.py runs after build_context_cache.py since it
    # reads the per-character cache files that script writes.
    cmds: list[list[str]] = [
        [py, "application/scripts/build_writing_rules_cache.py"],
        [py, "application/scripts/build_context_cache.py", "--dialogue-id", dialogue_id],
        [py, "application/scripts/build_character_briefs.py", "--dialogue-id", dialogue_id],
        [py, "application/scripts/extract_prose_tail.py", "--dialogue-id", dialogue_id],
        [py, "application/scripts/extract_last_turn.py", "--dialogue-id", dialogue_id],
    ]
    lorebook_cmd = [
        py, "application/scripts/build_active_lorebook.py", "--dialogue-id", dialogue_id,
    ]
    if user_prompt:
        lorebook_cmd += ["--user-prompt", user_prompt]
    cmds.append(lorebook_cmd)

    for cmd in cmds:
        subprocess.run(cmd, cwd=str(REPO), check=True)
