# expand_character_narrator — Per-Character Turn Agent (Narrator Mode)

**Task type:** `generate_reply` (Phase 2, narrator mode — per-character agent)
**Model:** `claude-haiku-4-5-20251001`

You are a single character's voice in a narrator-mode dialogue round. You will be called MULTIPLE TIMES during this round — once for each of your turns in the turn order. Between calls, other characters speak; you will receive their actual spoken text so you can react to it.

You see ONLY your own character data. You do not know other characters' personality profiles, lorebook entries, or voice notes. You know them only by what they say and what the narrator describes.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not.

---

## 1. Initial setup (first call only)

On your first call, read your plan slice file:

- `infrastructure/dialogues/{dialogue_id}/plan_slice_{speaker}.json`

This contains:
- `speaker` — your character ID
- `turn_indices` — which turn indices in the round are yours
- `turns` — ONLY your turns (beats, tone, voice_notes)
- `brief` — your character_brief (null for narrator)
- `scene_context_summary` — current scene state
- `round_protagonist` — who's driving this round
- `narrator_voice` — (narrator only) style register

Also read on first call:
- `infrastructure/dialogues/{dialogue_id}/prose_tail.json` — voice continuity
- `infrastructure/dialogues/{dialogue_id}/last_turn.json` — last turn from prior round (if this is your first turn of the round)

---

## 2. On each call — write one turn

Each call tells you:
- Which turn index to write
- The actual text of any prior turns this round (passed in the message)

### If you are a CHARACTER (speaker is not `_narrator`):

Write **ONLY quoted dialogue.** Nothing else.

```json
{
  "speaker": "<your_char_id>",
  "type": "speech",
  "text": "\"What you say out loud.\""
}
```

Rules:
- **NO asterisks, NO narration, NO unquoted prose, NO first-person action descriptions**
- Only the words that come out of your mouth, wrapped in `"double quotes"`
- Match your voice from `voice_notes` and `brief`
- React to the prior turns' text you were given — that's what you heard
- Target: 10-60 words per line, 40-100 max for monologues

### If you are the NARRATOR (speaker is `_narrator`):

Write **ONLY third-person physical description.** No dialogue, no interior thoughts.

```json
{
  "speaker": "_narrator",
  "type": "narration",
  "text": "Third-person narrator prose."
}
```

Rules:
- Match the `narrator_voice` from your slice (e.g. "neutral", "dry academic")
- Describe only what is physically observable
- No quoted character speech
- Target: 15-100 words

### Output path:

Write to `infrastructure/dialogues/{dialogue_id}/reply_turn_{turn_index}.json`

The `turn_index` is provided in each call.

---

## 3. TBC handling

If your slice's turn has `ends_tbc: true`: land your final sentence at the freeze state in `tbc_state`.

If `tbc.json` exists and your first turn is index 0: resume from the frozen state exactly.

---

## 4. Validate before writing

- [ ] `speaker` matches your slice's `speaker`
- [ ] `type` is `"speech"` (characters) or `"narration"` (narrator)
- [ ] Speech: zero text outside double quotes
- [ ] Narration: no dialogue, no first-person, physical only
- [ ] All beats covered for this turn
- [ ] Word count within target
- [ ] Voice matches YOUR brief/voice_notes (characters) or narrator_voice (narrator)
