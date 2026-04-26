"""Phase 0b — narrator → normal mode transition bridge.

Only runs when:
  - TAVERN_CHAT_MODE=normal in the env, AND
  - characters.json has "narrator": true (dialogue was started in narrator mode)

Generates a bridge scenario.json from goals.json + recent_chat.json + per-char
context caches, then flips characters.json["narrator"] to false and re-runs
build_context_cache.py to refresh the cache with the new scenario.

Tier 1 (Step 1): Required reads built from filesystem state.
"""

from __future__ import annotations

import json
import subprocess
import sys

from ...env import TavernConfig
from ...prompts import REPO, build_prompt, build_required_reads, per_character_context_caches
from ...sdk import spawn_agent


async def maybe_run(dialogue_id: str, cfg: TavernConfig) -> None:
    if cfg.chat_mode != "normal":
        return

    chars_path = REPO / "infrastructure" / "dialogues" / dialogue_id / "characters.json"
    if not chars_path.exists():
        return
    chars = json.loads(chars_path.read_text(encoding="utf-8"))
    if not chars.get("narrator"):
        return

    # Tier 1 manifest: bridge required + per-char caches present on disk.
    base = [
        f"infrastructure/dialogues/{dialogue_id}/goals.json",
        f"infrastructure/dialogues/{dialogue_id}/recent_chat.json",
    ]
    base.extend(per_character_context_caches(dialogue_id))
    required, absent = build_required_reads(base=base, optional=[], dialogue_id=dialogue_id)

    extra = [
        "Goal: bridge a narrator → normal mode transition. Generate scenario.json that "
        "describes the CURRENT scene state (from recent_chat.json), not the original "
        "greeting. Each participant gets a first-person scenario entry. openings is "
        "an empty array (mid-dialogue, past the opening). If goals are active, scenarios "
        "pick up the current beat; if completed, scenarios reflect the resolution.",
        "",
        f"Output path: infrastructure/dialogues/{dialogue_id}/scenario.json",
        "",
        "Schema:",
        json.dumps({
            "dialogue_id": dialogue_id,
            "generated_at": "<ISO 8601 now>",
            "mode_transition": True,
            "transitioned_from": "narrator",
            "participants": {
                "<char_id>": {
                    "name": "<display name>",
                    "scenario": "<1-3 paragraphs, first-person POV, current state>",
                    "openings": [],
                },
            },
        }, indent=2),
    ]

    prompt = build_prompt(
        instruction_file="(direct task — no instruction file; follow the schema below)",
        task_json={"dialogue_id": dialogue_id, "purpose": "narrator→normal bridge"},
        required_reads=required,
        absent_confirmed=absent,
        extra_lines=extra,
    )
    result = await spawn_agent(
        prompt, model="sonnet", allowed_tools=["Read", "Write"],
        label="phase0b transition",
        dialogue_id=dialogue_id,
    )
    if result.is_error:
        raise RuntimeError(f"transition bridge agent error: {result.text[:500]}")

    # Flip characters.json["narrator"] → false
    chars["narrator"] = False
    chars_path.write_text(json.dumps(chars, indent=2, ensure_ascii=False), encoding="utf-8")

    # Re-run context cache to pick up the new scenario
    subprocess.run(
        [sys.executable, "application/scripts/build_context_cache.py",
         "--dialogue-id", dialogue_id],
        cwd=str(REPO),
        check=True,
    )
