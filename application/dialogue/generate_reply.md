# generate_reply — Sonnet Agent Instructions

**Task type:** `generate_reply`
**Model:** `claude-sonnet-4-6`

You are given a queue item. Execute it completely, then clear it from the queue.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/generate_reply.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

---

## 1. Read the queue item

From `infrastructure/queue/queue.json`, find the item with `"type": "generate_reply"`. Extract:

- `input.dialogue_id`
- `input.replying_char_id` — the character who speaks this round (may be one or both)
- `input.user_prompt` — optional scene direction from the user
- `output_path` — where to write/update results

---

## 2. Read scene context

Read the following files:

- `infrastructure/dialogues/{dialogue_id}/scenario.json` — scene premise and each character's scenario framing
- `infrastructure/dialogues/{dialogue_id}/recent_chat.json` — recent dialogue context (last ~10 turns)
- `infrastructure/dialogues/{dialogue_id}/memory.json` — general scene memory, if it exists
- Character `data.json` for each character in the scene — **read only the fields listed below**

Do not read `full_chat.json` — recent_chat.json is the context window.

**Fields to extract from each character's `data.json`:**

| Section | Fields |
|---|---|
| `identity` | `name`, `gender` |
| `appearance` | `summary`, `build` |
| `personality` | `core_traits`, `emotional_baseline`, `quirks`, `triggers` |
| `speech` | all fields (`voice_description`, `vocabulary_level`, `speech_patterns`, `sample_lines`) |
| `behavior` | `social_style`, `relationship_defaults`, `stress_behaviors` |

Do not read or load any other sections (`meta`, `lorebook`, `abilities`, `voice_archetype`, `dialogue_seeds`, `scenario_defaults`, `filter_tags`).

---

## 3. Generate the reply

Write a reply for `replying_char_id` that:

- Continues naturally from the last line in `recent_chat.json`
- Reflects the character's `personality`, `speech`, and `behavior` as defined in their `data.json`
- Honors the scenario framing from `scenario.json`
- Incorporates `user_prompt` if present — treat it as directorial steering, not dialogue
- Stays consistent with `memory.json` context if present
- Does not break the fourth wall or acknowledge being a character

---

## 4. Formatting rules

Follow `domain/dialogue/writing_rules.md` for all speech wrapping, action description perspective, inline rules, and paragraph breaks.

**Length:** Match the energy of the scene. A sharp, reactive beat may be 2–3 short paragraphs. A longer emotional or physical sequence may run more. Do not pad; do not truncate.

---

## 5. Update dialogue files

Each turn is a JSON object:

```json
{ "speaker": "<char_id>", "text": "<reply with \\n\\n paragraph breaks>" }
```

**`infrastructure/dialogues/{dialogue_id}/full_chat.json`** — append the new turn(s) to the array. This is the permanent record, it grows unboundedly.

**`infrastructure/dialogues/{dialogue_id}/recent_chat.json`** — append the new turn(s), then **trim to the last 10 entries** before writing. This is the context window; keeping it fixed-size prevents cost growth over long dialogues.

No other fields. Write valid JSON arrays.

---

## 6. Clear the queue item

After writing the dialogue files, remove the processed item from `infrastructure/queue/queue.json`. If the queue is now empty, write `[]`.

---

## 7. Validate before writing

- [ ] Reply is consistent with character voice and personality from `data.json`
- [ ] All speech in `"double quotes"`, actions in `*asterisks*`, interior thoughts in `` `backticks` ``
- [ ] Interior thoughts always on their own line — never inline with action beats or dialogue
- [ ] Distinct paragraphs separated with `\n\n` — not a single run-on block
- [ ] `user_prompt` direction honored if provided
- [ ] `full_chat.json` appended (unbounded)
- [ ] `recent_chat.json` appended then trimmed to last 10 entries
- [ ] Queue item removed
