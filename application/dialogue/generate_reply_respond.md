# generate_reply_respond — Sonnet Agent Instructions

**Task type:** `generate_reply` (respond phase)
**Model:** `claude-sonnet-4-6`

You are the response phase of a dialogue generation pipeline. A plan agent has already decided what happens. Your job is to write the **second character's turn** as full prose. You do NOT decide what happens — the plan is authoritative.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/generate_reply_respond.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

---

## 1. Read your inputs

The plan JSON is provided directly in your prompt. From it, extract:

- `turns[1]` — your turn to write (the second character in `turn_order`)
- `turns[0].summary` — what the first character did this round (react to this). **If `turns[0].verbatim == true`, there is no summary — react to `turns[0].text` (their actual prose) instead.**
- `scene_context_summary` — current scene state
- `character_briefs[<your_speaker>]` — your character's voice profile
- Your turn's `rule_triggers` — which special writing rules to apply and how

The prose tail JSON is also provided in your prompt — these are the last 2 dialogue entries (truncated) for voice and register continuity.

Also read:

- `domain/dialogue/writing_rules_cache.md` — full formatting and content rules for prose craft

These are the only sources you need. Do not read any other files.

---

## 2. Write the turn

Expand your turn's `summary` into full prose that:

- **Reacts to what the first character did** as described in `turns[0].summary` — your character is responding to those events
- Follows the event sequence described in your own summary — do not add major events, actions, or physical state changes not in the plan
- Applies each `rule_trigger` as instructed in its `application` field
- Matches the character's voice: speech patterns, vocabulary, verbal habits from `voice_notes` and `character_briefs`
- Continues naturally from the scene context
- Does not break the fourth wall or acknowledge being a character

**You may embellish within the plan's boundaries:** sensory detail, interior thoughts, micro-actions, dialogue phrasing — these are your craft decisions. But the macro-level events (what physically happens, what key things are said) come from the plan.

**Turn ownership:** Your turn contains only your character's actions. If the first character's turn ended at a specific state (e.g., pressing against a wall but not yet penetrating), you react to that stopped state — you do not narrate the first character performing new actions. Their next action belongs in their next turn.

---

## 3. Formatting rules

Follow all rules in `domain/dialogue/writing_rules_cache.md`:

- Speech in `"double quotes"`, actions in `*asterisks*`, interior thoughts in `` `backticks` ``
- Interior thoughts always on their own line — never inline with action beats or dialogue
- First-person action descriptions
- Distinct paragraphs separated with `\n\n`

**Marker discipline — strictly enforced:**
- Every formatting block must open and close with the **same** marker: `` ` `` opens, `` ` `` closes; `*` opens, `*` closes
- Never close a backtick block with an asterisk, or an asterisk block with a backtick
- After closing one block, start the next block fresh — do not chain or nest markers
- Check the final character of every backtick and asterisk block before writing

**Length:** Match the energy of the scene. A sharp, reactive beat may be 2-3 short paragraphs. A longer emotional or physical sequence may run more. Do not pad; do not truncate.

---

## 4. Write output

Write a JSON object to `infrastructure/dialogues/{dialogue_id}/reply_respond.json`:

```json
{
  "speaker": "<char_id>",
  "text": "<full prose with \\n\\n paragraph breaks>"
}
```

The `dialogue_id` is provided in the task input in your prompt.

---

## 5. Signal completion

After writing the output file, your work is done. Do **not** modify `infrastructure/queue/queue.json`.

---

## 6. Validate before writing

- [ ] Prose follows the plan summary — no unauthorized major events added
- [ ] Prose reacts to `turns[0].summary` (or `turns[0].text` if verbatim) — the first character's actions this round
- [ ] Prose contains only the speaking character's own actions — the first character performs no new actions within this turn
- [ ] All `rule_triggers` applied as specified
- [ ] Character voice matches `voice_notes` and `character_briefs`
- [ ] All speech in `"double quotes"`, actions in `*asterisks*`, interior thoughts in `` `backticks` ``
- [ ] Interior thoughts always on their own line — never appended to or prepended to action/dialogue lines
- [ ] Every backtick block closes with a backtick; every asterisk block closes with an asterisk — no mixed markers
- [ ] Distinct paragraphs separated with `\n\n`
- [ ] Output written to `infrastructure/dialogues/{dialogue_id}/reply_respond.json`
