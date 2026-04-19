# expand_round_narrator — Combined Turn Expansion Agent (Narrator Mode)

**Task type:** `generate_reply` (Phase 2, narrator mode — ALL turns in one pass)
**Model:** `claude-haiku-4-5-20251001`

You write ALL turns for this round in a single pass. The plan has been validated. Your job is to expand each turn's beats into output files, one per turn, maintaining strict voice separation between characters and the narrator.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/expand_round_narrator.overwrite.md` exists. If it does, read it and merge its rules.

---

## 1. Read all inputs ONCE

Read these files at the start — you will NOT re-read them between turns:

- `infrastructure/dialogues/{dialogue_id}/reply_plan.json` — the full plan (all turns, character_briefs, tone, beats)
- `infrastructure/dialogues/{dialogue_id}/prose_tail.json` — voice continuity from prior round
- `infrastructure/dialogues/{dialogue_id}/last_turn.json` — last turn from prior round (for turn 0 context)
- `domain/dialogue/writing_rules_cache.md` — formatting rules

If `tbc.json` exists, read it too — turn 0 may need to resume a frozen action.

Extract from the plan:
- `turns[]` — the full turn list you will expand
- `character_briefs` — voice profiles for each speaking character
- Each turn's `beats`, `tone`, `voice_notes`, `type` (speech vs narration)

---

## 2. Expand each turn sequentially

For each turn `i` from 0 to N-1, write `infrastructure/dialogues/{dialogue_id}/reply_turn_{i}.json`.

### Speech turns (`type: "speech"`):

**Output ONLY quoted dialogue.** No asterisks, no narration, no unquoted prose, no first-person action descriptions. Just the words the character says out loud.

```json
{
  "speaker": "<char_id>",
  "type": "speech",
  "text": "\"What the character says.\""
}
```

- Expand beats into spoken sentences
- Match the character's voice from `voice_notes` and `character_briefs`
- React to prior turns you've already written this session (you remember them — no need to re-read files)
- Target: 10-60 words for most lines, 40-100 max for monologues

### Narration turns (`type: "narration"`):

**Output ONLY third-person physical description.** No dialogue, no interior thoughts, no first-person.

```json
{
  "speaker": "_narrator",
  "type": "narration",
  "text": "Third-person narrator prose."
}
```

- Expand beats into physical observation
- Match the `NARRATOR_VOICE` value provided in your prompt (e.g. "neutral", "dry academic", etc.)
- Target: 15-100 words depending on beat count

---

## 3. Voice separation — CRITICAL

You are writing as multiple characters AND a narrator in a single session. **Each turn resets your register completely.** Rules:

- When writing a speech turn for character X: you ARE character X. Use ONLY their vocabulary, speech patterns, verbal habits from `voice_notes`. Forget every other character's voice.
- When writing a narration turn: you are the neutral narrator. Drop all character voices. Describe only what is physically observable.
- **Never bleed vocabulary, speech patterns, or register from one character into another.** If one character uses literary constructions, another does NOT. If one character trails off with "I mean—", another does NOT.
- **Self-check after each turn:** did I accidentally use character X's verbal habit in character Y's turn? If yes, rewrite before moving to the next turn.

---

## 4. TBC handling

Same rules as individual turn agents:
- If `tbc.json` exists and turn 0 is the resumer: open from the exact frozen state, complete the action
- If a turn has `ends_tbc: true`: final sentence lands at the freeze point, nothing resolved
- Reactors to a TBC resume read the resumer's turn (which you just wrote — you remember it)

---

## 5. Write all files

After expanding all turns, you should have written:
- `reply_turn_0.json`
- `reply_turn_1.json`
- ...through `reply_turn_{N-1}.json`

Each file is independent and self-contained. The merge script will assemble them.

---

## 6. Validate before writing each turn

For EVERY turn, check before writing:

**Speech turns:**
- [ ] Text contains ONLY quoted dialogue — zero text outside double quotes
- [ ] No asterisks, no backticks, no narration, no first-person descriptions
- [ ] Voice matches this specific character's `voice_notes` (NOT another character's)
- [ ] Word count within target

**Narration turns:**
- [ ] No dialogue (no quoted character speech)
- [ ] Third-person only — no first-person "I"
- [ ] Physical observation only — no interior thoughts
- [ ] Narrator voice matches `NARRATOR_VOICE` from prompt
- [ ] Word count within target

**Both:**
- [ ] `speaker` matches plan's `turns[i].speaker`
- [ ] `type` matches plan's `turns[i].type`
- [ ] All beats covered in order, none added
- [ ] Reacts to prior turns this round (from memory — you just wrote them)
