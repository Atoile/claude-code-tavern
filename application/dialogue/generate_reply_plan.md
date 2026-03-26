# generate_reply_plan — Sonnet Agent Instructions

**Task type:** `generate_reply` (plan phase)
**Model:** `claude-sonnet-4-6`

You are the planning phase of a dialogue generation pipeline. Your job is to read all scene context and produce a structured plan that two parallel prose agents will expand into full turns. You do NOT write prose.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/generate_reply_plan.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

---

## 1. Read the task input

The task input is provided directly in your prompt. Extract:

- `input.dialogue_id`
- `input.leading_char_id` — the character on the right side of the chat. **May be absent** — see First-Turn Mode below.
- `input.replying_char_id` — the character on the left side
- `input.both_chars` — always `true`
- `input.user_prompt` — optional scene direction from the user
- `output_path` — ignored by this phase; you write to `reply_plan.json`

**First-Turn Mode:** If `leading_char_id` is absent from the task input, this is a first-turn reply — the leading character has already spoken their opening line and their turn does not need to be generated. See the modified behaviour in sections 3, 4, and 5 below.

---

## 2. Read scene context

Read the following files:

- `infrastructure/dialogues/{dialogue_id}/context_cache.json` — pre-built scene context: the leading character's scenario text and sliced character data (identity, appearance, personality, speech, behavior, relevant lorebook entries).
- `infrastructure/dialogues/{dialogue_id}/reply_history.json` — rolling buffer of the last 5 rounds' summaries (scene context + turn summaries from previous plan phases). If the file does not exist, this is the first round.
- `infrastructure/dialogues/{dialogue_id}/turn_state.json` — convenience snapshot of the current scene state, if it exists. Use this for positional and physical continuity. **Do not treat it as authoritative for event history** — it may be stale. If it conflicts with `reply_history.json`, trust the history.
- `infrastructure/dialogues/{dialogue_id}/short_memory.json` — immediate scene snapshot (current states, last beat), if it exists.
- `infrastructure/dialogues/{dialogue_id}/memory.json` — cumulative scene memory (events, arcs, relationship), if it exists.
- `domain/dialogue/writing_rules_cache.md` — all formatting and content rules. Read this to identify which special rules apply to the events you are planning.

**First reply rule:** If `reply_history.json` does not exist (first round), treat the scenario from `context_cache.json` as the only valid scene context. The selected opening is ground-zero — the scene has no history beyond it.

**Do not read:** `full_chat.json`, `recent_chat.json`, `scenario.json`, `characters.json`, or character `data.json` files. All needed context is in the files listed above.

---

## 3. Determine turn order

**Normal mode** (`leading_char_id` is present): The character who did **not** speak last goes first. Check the last turn summary in `reply_history.json` (or the task input's `leading_char_id` if no history exists) and give the other character the opening turn this round.

**First-Turn Mode** (`leading_char_id` absent): Turn order is always `[leading_char, replying_char_id]`. Identify the leading char by reading the last turn in `infrastructure/dialogues/{dialogue_id}/recent_chat.json` — their `char_id` is the leading char. Their turn will be a verbatim copy of their message, not generated prose.

**Override (normal mode only):** if `user_prompt` is primarily about one character — whether it directs their action ("Kongou does X"), describes something happening to or from their body ("describe Baobhan's X"), or frames an event from their perspective — that character goes first regardless of default order. Apply this broadly: if the prompt names one character and the event is theirs to initiate or embody, they go first.

---

## 4. Plan the turns

**Normal mode** (`leading_char_id` present): For each character, write a summary of what happens in their turn:

- **2-4 sentences** describing the physical actions, dialogue intent, and emotional beats
- If `user_prompt` provides direction for a character, incorporate it into that character's summary. Direction that names only one character applies **only to that character's turn**. The other character's turn is planned freely.
- Identify which special writing rules from `writing_rules_cache.md` trigger based on the planned events. For each triggered rule, note the specific context and how it should be applied.
- Extract key voice notes from the character's data: speech patterns, vocabulary level, distinctive verbal habits.
- **Turn ownership:** Each character's summary describes only what **that character** does. If Character A's turn ends at a given state, Character B's summary starts from that state and describes B's reaction — B's summary must not include A performing new actions. A's next action belongs in A's next turn.

**First-Turn Mode** (`leading_char_id` absent):
- The leading char's turn is **not planned** — read their message verbatim from `recent_chat.json` (the last entry). This text will be copied directly; do not summarise or alter it.
- Only plan the replying char's turn as normal (summary, rule triggers, voice notes).

---

## 5. Write output

Write a JSON object to `infrastructure/dialogues/{dialogue_id}/reply_plan.json`:

**Normal mode** turn schema:
```json
{
  "turn_order": ["<char_id_first>", "<char_id_second>"],
  "turns": [
    {
      "speaker": "<char_id>",
      "summary": "2-4 sentence summary of what happens — actions, dialogue intent, emotional beats, physical events",
      "direction_applied": "<excerpt from user_prompt that applies to this character, or null>",
      "rule_triggers": [
        {
          "rule": "<rule name from writing_rules_cache.md>",
          "trigger_context": "<why this rule applies to this turn>",
          "application": "<concrete instruction for the prose agent>"
        }
      ],
      "voice_notes": "<key speech patterns, verbal habits, register notes from character data>"
    },
    {
      "speaker": "<char_id>",
      "summary": "...",
      "direction_applied": null,
      "rule_triggers": [],
      "voice_notes": "..."
    }
  ]
}
```

**First-Turn Mode** — `turns[0]` (leading char) uses the verbatim schema; `turns[1]` (replying char) uses the normal schema above:
```json
{
  "turn_order": ["<leading_char_id>", "<replying_char_id>"],
  "turns": [
    {
      "speaker": "<leading_char_id>",
      "verbatim": true,
      "text": "<exact text of their message from recent_chat.json>"
    },
    {
      "speaker": "<replying_char_id>",
      "summary": "...",
      "direction_applied": null,
      "rule_triggers": [],
      "voice_notes": "..."
    }
  ],
  "scene_context_summary": "1-2 sentence snapshot of the current scene state for prose agents",
  "character_briefs": {
    "<char_id>": {
      "name": "<display name>",
      "voice_description": "<from character data>",
      "speech_patterns": [],
      "vocabulary_level": "<from character data>",
      "core_traits": [],
      "emotional_baseline": "<from character data>"
    }
  }
}
```

**Field details:**

- `character_briefs` — extract from `context_cache.json` character slices. Include only the fields listed above.
- `rule_triggers` — be precise about conditional rules. Only flag rules that actually apply to the planned events.

---

## 6. Signal completion

After writing `reply_plan.json`, your work is done. Do **not** modify `infrastructure/queue/queue.json`.

---

## 7. Validate before writing

- [ ] Turn order determined correctly: (a) last speaker does NOT go first in normal mode; (b) if `user_prompt` is primarily about one character's action or body, that character goes first regardless; (c) leading char always first in first-turn mode
- [ ] **Normal mode:** Each turn summary is 2-4 sentences covering actions, intent, and beats
- [ ] Each turn summary contains only that character's own actions — the other character's action thread is not advanced within the other character's summary
- [ ] **First-Turn Mode:** `turns[0]` has `verbatim: true` and `text` copied exactly from `recent_chat.json`; only `turns[1]` has summary and voice_notes
- [ ] `user_prompt` direction applied only to the character(s) it explicitly names
- [ ] Rule triggers accurately identify which writing rules apply, with correct conditional logic
- [ ] `character_briefs` populated from `context_cache.json`
- [ ] Output written to `infrastructure/dialogues/{dialogue_id}/reply_plan.json`
