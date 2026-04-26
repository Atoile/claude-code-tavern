"""Phase 1 — plan.

Mode-routed:
  - normal   → generate_reply_plan.md (Step 1: static prompt, Tier 1 deferred)
  - narrator → generate_reply_plan_narrator.md (Step 1: Tier 1 manifest)

Both branches use the model selected by cfg.planner (TAVERN_PLANNER env).
"""

from __future__ import annotations

import json
from typing import Any, cast

from ...env import TavernConfig
from ...prompts import REPO, build_prompt, build_required_reads, per_character_context_caches
from ...sdk import spawn_agent


def _last_character_speaker(dialogue_id: str) -> str | None:
    """Find the most recent NON-narrator speaker.

    Walks reply_history.json backwards first; if absent or empty (e.g. first
    reply round where the only prior turn is the greeting), falls back to
    last_turn.json's speaker field. Returns None only when neither source
    yields a character speaker.
    """
    dlg = REPO / "infrastructure" / "dialogues" / dialogue_id
    history_path = dlg / "reply_history.json"
    if history_path.exists():
        try:
            history_raw: Any = json.loads(history_path.read_text(encoding="utf-8")) or []
        except (json.JSONDecodeError, OSError):
            history_raw = []
        history: list[Any] = cast(list[Any], history_raw) if isinstance(history_raw, list) else []
        for entry in reversed(history):
            if not isinstance(entry, dict):
                continue
            entry_d: dict[str, Any] = cast(dict[str, Any], entry)
            speaker: Any = entry_d.get("speaker")
            if isinstance(speaker, str) and speaker and speaker != "_narrator":
                return speaker

    # Fallback: last_turn.json (greeting / opening turn that hasn't been
    # rolled into reply_history yet — common on first reply round).
    last_turn_path = dlg / "last_turn.json"
    if last_turn_path.exists():
        try:
            last_turn_raw: Any = json.loads(last_turn_path.read_text(encoding="utf-8")) or {}
            last_turn: dict[str, Any] = (
                cast(dict[str, Any], last_turn_raw) if isinstance(last_turn_raw, dict) else {}
            )
            speaker = last_turn.get("speaker")
            if isinstance(speaker, str) and speaker and speaker != "_narrator":
                return speaker
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _round_metadata(dialogue_id: str, cfg: TavernConfig) -> dict[str, Any]:
    """Pre-compute meta-state the planner would otherwise re-derive.

    Inlined into the planner prompt so the agent skips Tier-1/Tier-2/Tier-3 etc.
    scaffolding work and goes straight to creative decisions (speakers, beats,
    scene_anchor). All fields are deterministic Python — no model tokens.
    """
    dlg = REPO / "infrastructure" / "dialogues" / dialogue_id

    # reply_history (may be missing or empty)
    history: list[dict[str, Any]] = []
    history_path = dlg / "reply_history.json"
    if history_path.exists():
        try:
            history_raw: Any = json.loads(history_path.read_text(encoding="utf-8")) or []
        except (json.JSONDecodeError, OSError):
            history_raw = []
        if isinstance(history_raw, list):
            for e in cast(list[Any], history_raw):
                if isinstance(e, dict):
                    history.append(cast(dict[str, Any], e))

    # characters.json — required (frontend always writes it before queuing)
    chars: dict[str, Any] = {}
    chars_path = dlg / "characters.json"
    if chars_path.exists():
        try:
            chars_raw: Any = json.loads(chars_path.read_text(encoding="utf-8")) or {}
            if isinstance(chars_raw, dict):
                chars = cast(dict[str, Any], chars_raw)
        except (json.JSONDecodeError, OSError):
            pass
    participants_raw: Any = chars.get("participants") or {}
    if isinstance(participants_raw, dict):
        participants = sorted(cast(dict[str, Any], participants_raw).keys())
    else:
        participants = []
    player_id_raw: Any = chars.get("player_id")
    player_id: str | None = player_id_raw if isinstance(player_id_raw, str) else None

    # tbc state
    tbc_active = (dlg / "tbc.json").exists()

    # most recent character speaker
    last_speaker = _last_character_speaker(dialogue_id) or "<none — first reply round>"

    # silence fatigue: count consecutive entries in reply_history (newest first)
    # where the participant is absent. For 2-char scenes this is mostly noise
    # (both speak every round) but it's free to compute.
    fatigue: dict[str, int] = {}
    for char_id in participants:
        if char_id == player_id:
            continue
        silent = 0
        for entry in reversed(history):
            spk: Any = entry.get("speaker")
            if spk == char_id:
                break
            if isinstance(spk, str) and spk and spk != "_narrator":
                silent += 1
        fatigue[char_id] = silent

    # files actually on disk (per-round + memory-tier signals)
    files_present: list[str] = []
    for name in ("last_turn.json", "reply_history.json", "tbc.json",
                 "turn_state.json", "short_memory.json", "memory.json"):
        if (dlg / name).exists():
            files_present.append(name)

    # round number: number of distinct round-starts in history + 1
    round_starts = sum(1 for e in history if "scene_context" in e)
    round_number = (round_starts or len(history)) + 1 if history else 1

    return {
        "round_number": round_number,
        "is_first_reply_round": not history,
        "chat_mode": cfg.chat_mode,
        "verbatim_mode": cfg.verbatim,
        "participants": participants,
        "player_id": player_id,
        "last_character_speaker": last_speaker,
        "tbc_active": tbc_active,
        "silence_fatigue_rounds": fatigue,
        "files_present": files_present,
    }


def _format_round_metadata(meta: dict[str, Any]) -> list[str]:
    """Format _round_metadata() output as the planner-prompt block."""
    participants_list = cast(list[str], meta['participants'])
    files_present_list = cast(list[str], meta['files_present'])
    lines = [
        "ROUND METADATA (orchestrator-computed — trust these, do not re-derive):",
        f"- Round number: {meta['round_number']}"
        + (" (first reply round)" if meta['is_first_reply_round'] else ""),
        f"- Mode: TAVERN_CHAT_MODE={meta['chat_mode']}, TAVERN_VERBATIM={meta['verbatim_mode']}",
        f"- Participants: {', '.join(participants_list) or '<none>'}",
        f"- Player character: {meta['player_id'] or 'none (director mode)'}",
        f"- Most recent character speaker: {meta['last_character_speaker']}",
        f"- TBC state: {'active (resume required from tbc.json)' if meta['tbc_active'] else 'none pending'}",
    ]
    fatigue_map = cast(dict[str, int], meta["silence_fatigue_rounds"])
    if fatigue_map:
        sf = ", ".join(f"{k}={v}" for k, v in fatigue_map.items())
        lines.append(f"- Silence fatigue (rounds since last spoke): {sf}")
    lines.append(f"- Files present: {', '.join(files_present_list) or '<none>'}")
    return lines


# ─── Path lists ─────────────────────────────────────────────────────────────

_NARRATOR_BASE = [
    "infrastructure/dialogues/{dialogue_id}/context_cache.json",
    "infrastructure/dialogues/{dialogue_id}/goals.json",
    "infrastructure/dialogues/{dialogue_id}/active_lorebook.json",
    "infrastructure/dialogues/{dialogue_id}/characters.json",
    "domain/dialogue/writing_rules_cache.md",
]
_NARRATOR_OPTIONAL = [
    "infrastructure/dialogues/{dialogue_id}/reply_history.json",
    "infrastructure/dialogues/{dialogue_id}/tbc.json",
    # last_turn.json: most recent turn's full prose (greeting on first reply
    # round). Authoritative for delta extraction.
    "infrastructure/dialogues/{dialogue_id}/last_turn.json",
    # scene_state.json: persistent canonical scene state (time, location,
    # proximity, positions, wardrobe, in_progress_action). Created on the
    # first reply round, updated each round by the planner with deltas from
    # last_turn. Survives across rounds — NOT in _STALE_ARTIFACTS cleanup.
    "infrastructure/dialogues/{dialogue_id}/scene_state.json",
    "application/dialogue/generate_reply_plan_narrator.overwrite.md",
]

_NORMAL_BASE = [
    "infrastructure/dialogues/{dialogue_id}/context_cache.json",
    "infrastructure/dialogues/{dialogue_id}/active_lorebook.json",
    "infrastructure/dialogues/{dialogue_id}/characters.json",
    "domain/dialogue/writing_rules_cache.md",
]
_NORMAL_OPTIONAL = [
    "infrastructure/dialogues/{dialogue_id}/reply_history.json",
    "infrastructure/dialogues/{dialogue_id}/tbc.json",
    "infrastructure/dialogues/{dialogue_id}/turn_state.json",
    "infrastructure/dialogues/{dialogue_id}/short_memory.json",
    "infrastructure/dialogues/{dialogue_id}/memory.json",
    "infrastructure/dialogues/{dialogue_id}/last_turn.json",  # see narrator note above
    "infrastructure/dialogues/{dialogue_id}/scene_state.json",  # see narrator note above
    "application/dialogue/generate_reply_plan.overwrite.md",
]


async def run_phase_1(dialogue_id: str, item: dict[str, Any], cfg: TavernConfig) -> None:
    if cfg.chat_mode == "narrator":
        await _run_narrator(dialogue_id, item, cfg)
    else:
        await _run_normal(dialogue_id, item, cfg)


async def _run_narrator(dialogue_id: str, item: dict[str, Any], cfg: TavernConfig) -> None:
    # Tier 1 manifest: prune absent optionals + per-character context caches.
    base = list(_NARRATOR_BASE) + per_character_context_caches(dialogue_id)
    required, absent = build_required_reads(
        base=base,
        optional=_NARRATOR_OPTIONAL,
        dialogue_id=dialogue_id,
    )

    # Strip output_path so the planner can't shortcut to pending_turns.json
    # (writes reply_plan.json only).
    sanitized_item = {k: v for k, v in item.items() if k != "output_path"}

    extra: list[str] = [
        "OUTPUT CONTRACT:",
        f"- Write ONLY infrastructure/dialogues/{dialogue_id}/reply_plan.json.",
        "- DO NOT write pending_turns.json or any other file.",
        "",
        *_format_round_metadata(_round_metadata(dialogue_id, cfg)),
    ]
    # Pre-compute the expected last character speaker from reply_history.json
    # and inline as a hard requirement. Closes the 2b_turn_order rule loop —
    # planner can't accidentally swap final speakers because the rule is
    # spelled out per-round with the actual char_id.
    expected_last = _last_character_speaker(dialogue_id)
    if expected_last:
        extra.extend([
            "",
            "TURN-ORDER HARD REQUIREMENT:",
            f"- Most recent character speaker in reply_history is '{expected_last}'.",
            f"- The LAST character entry in turn_order this round MUST be '{expected_last}'.",
            "  (Trailing _narrator entries after that character are fine.)",
            "- Violating this triggers an instant replan (orchestrator-detected critical).",
        ])

    prompt = build_prompt(
        instruction_file="application/dialogue/generate_reply_plan_narrator.md",
        task_json=sanitized_item,
        required_reads=required,
        absent_confirmed=absent,
        extra_lines=extra,
    )
    # Adaptive thinking on Sonnet — model self-sizes per round (light on easy
    # scenes, scales up on TBC-resume / multi-character pivot rounds).
    result = await spawn_agent(
        prompt, model=cfg.planner, label="phase1 plan/narrator",
        thinking_budget="adaptive" if cfg.planner == "sonnet" else None,
        dialogue_id=dialogue_id,
    )
    if result.is_error:
        raise RuntimeError(f"narrator planner agent error: {result.text[:500]}")


async def _run_normal(dialogue_id: str, item: dict[str, Any], cfg: TavernConfig) -> None:
    # Step 1 scope says "no Tier 1 for normal mode", but probing the overwrite
    # path universally costs nothing in Python and prevents wasted Glob calls
    # on the agent side. Keep this minimal — full Tier 1 for normal mode lands
    # in Step 2.
    base = list(_NORMAL_BASE) + per_character_context_caches(dialogue_id)
    required, absent = build_required_reads(
        base=base,
        optional=_NORMAL_OPTIONAL,
        dialogue_id=dialogue_id,
    )
    sanitized_item = {k: v for k, v in item.items() if k != "output_path"}

    extra: list[str] = [
        "OUTPUT CONTRACT:",
        f"- Write ONLY infrastructure/dialogues/{dialogue_id}/reply_plan.json.",
        "- DO NOT write pending_turns.json or any other file.",
        "",
        *_format_round_metadata(_round_metadata(dialogue_id, cfg)),
    ]
    expected_last = _last_character_speaker(dialogue_id)
    if expected_last:
        extra.extend([
            "",
            "TURN-ORDER HARD REQUIREMENT:",
            f"- Most recent character speaker in reply_history is '{expected_last}'.",
            f"- The LAST entry in turn_order this round MUST be '{expected_last}'.",
            "- Violating this triggers an instant replan (orchestrator-detected critical).",
        ])

    prompt = build_prompt(
        instruction_file="application/dialogue/generate_reply_plan.md",
        task_json=sanitized_item,
        required_reads=required,
        absent_confirmed=absent,
        extra_lines=extra,
    )
    result = await spawn_agent(
        prompt, model=cfg.planner, label="phase1 plan/normal",
        thinking_budget="adaptive" if cfg.planner == "sonnet" else None,
        dialogue_id=dialogue_id,
    )
    if result.is_error:
        raise RuntimeError(f"normal planner agent error: {result.text[:500]}")
