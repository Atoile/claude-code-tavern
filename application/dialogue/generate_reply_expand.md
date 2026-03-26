# generate_reply_expand — Sonnet Agent Instructions

**Task type:** `generate_reply` (expand phase)
**Model:** `claude-sonnet-4-6`

You are the expansion phase of a dialogue generation pipeline. A plan agent has already decided what happens. Your job is to write the **first character's turn** as full prose. You do NOT decide what happens — the plan is authoritative.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/generate_reply_expand.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

---

## 1. Read your inputs

The plan JSON is provided directly in your prompt. From it, extract:

- `turns[0]` — your turn to expand (the first character in `turn_order`)
- `scene_context_summary` — current scene state
- `character_briefs[<your_speaker>]` — your character's voice profile
- Your turn's `rule_triggers` — which special writing rules to apply and how

**Verbatim check:** If `turns[0].verbatim == true`, this turn is already written. Skip to section 4 — write `reply_expand.json` using `turns[0].text` verbatim, with no prose generation.

The prose tail JSON is also provided in your prompt — these are the last 2 dialogue entries (truncated) for voice and register continuity.

Also read (only when NOT in verbatim mode):

- `domain/dialogue/writing_rules_cache.md` — full formatting and content rules for prose craft

These are the only sources you need. Do not read any other files.

---

## 2. Write the turn

Expand your turn's `summary` into full prose that:

- Follows the event sequence described in the summary — do not add major events, actions, or physical state changes not in the plan
- Applies each `rule_trigger` as instructed in its `application` field
- Matches the character's voice: speech patterns, vocabulary, verbal habits from `voice_notes` and `character_briefs`
- Continues naturally from the prose tail (last dialogue entries)
- Does not break the fourth wall or acknowledge being a character

**You may embellish within the plan's boundaries:** sensory detail, interior thoughts, micro-actions, dialogue phrasing — these are your craft decisions. But the macro-level events (what physically happens, what key things are said) come from the plan.

**Turn ownership:** Your turn contains only your character's actions. If the previous round ended at a specific state, you continue from there — you do not narrate the other character performing new actions within your turn. Their actions belong in their own turn.

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

Write a JSON object to `infrastructure/dialogues/{dialogue_id}/reply_expand.json`:

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

- [ ] **If verbatim mode:** `turns[0].text` copied exactly to output — no modifications
- [ ] **If normal mode:** Prose follows the plan summary — no unauthorized major events added
- [ ] Prose contains only the speaking character's own actions — the other character performs no new actions within this turn
- [ ] All `rule_triggers` applied as specified (normal mode only)
- [ ] Character voice matches `voice_notes` and `character_briefs` (normal mode only)
- [ ] All speech in `"double quotes"`, actions in `*asterisks*`, interior thoughts in `` `backticks` ``
- [ ] Interior thoughts always on their own line — never appended to or prepended to action/dialogue lines
- [ ] Every backtick block closes with a backtick; every asterisk block closes with an asterisk — no mixed markers
- [ ] Distinct paragraphs separated with `\n\n`
- [ ] Output written to `infrastructure/dialogues/{dialogue_id}/reply_expand.json`
