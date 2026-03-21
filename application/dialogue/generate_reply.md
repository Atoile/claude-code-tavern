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

**First reply rule:** If `recent_chat.json` contains exactly one entry (the opening line), treat that entry and the scenario as the only valid scene context. Do not draw on, infer from, or let bleed through any of the unselected openings in `scenario.json`. The selected opening is ground-zero — the scene has no history beyond it.
- `infrastructure/dialogues/{dialogue_id}/short_memory.json` — immediate scene snapshot (current states, last beat), if it exists — treat as highest-priority context after `recent_chat.json`
- `infrastructure/dialogues/{dialogue_id}/memory.json` — cumulative scene memory (events, arcs, relationship), if it exists
- Character `data.json` for each character in the scene — **read only the fields listed below**

**Do not read `full_chat.json` for context.** It is only touched in step 5 to append new turns. `recent_chat.json` is the sole context window.

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

**Turn order when `both_chars: true`:**

- **Default:** the character who did *not* speak last in `recent_chat.json` goes first. Check the `speaker` of the final entry and give the other character the opening turn this round.
- **Override:** if `user_prompt` explicitly directs a specific character's action (e.g. "as Gary Stu does X…"), that character goes first regardless of default order.

Write a reply for `replying_char_id` that:

- Continues naturally from the last line in `recent_chat.json`
- Reflects the character's `personality`, `speech`, and `behavior` as defined in their `data.json`
- Honors the scenario framing from `scenario.json`
- Incorporates `user_prompt` if present — treat it as directorial steering, not dialogue
- Stays consistent with `memory.json` context if present
- Does not break the fourth wall or acknowledge being a character

---

## 4. Formatting rules

Follow `domain/dialogue/writing_rules.md` for all speech wrapping, action description perspective, inline rules, and paragraph breaks. Also check whether `domain/dialogue/writing_rules.overwrite.md` exists — if it does, read it and apply its rules on top of the baseline (overwrite rules take precedence where they conflict).

**Length:** Match the energy of the scene. A sharp, reactive beat may be 2–3 short paragraphs. A longer emotional or physical sequence may run more. Do not pad; do not truncate.

---

## 5. Write output

Each turn is a JSON object:

```json
{ "speaker": "<char_id>", "text": "<reply with \\n\\n paragraph breaks>" }
```

Write a JSON array of the new turn object(s) to `output_path` from the queue item.

Do not write to `full_chat.json` or `recent_chat.json` — the orchestrator appends them after you finish via `application/scripts/append_turns.py`.

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
- [ ] New turns written as a JSON array to `output_path`
- [ ] Queue item removed
