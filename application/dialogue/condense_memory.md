# condense_memory — Sonnet Agent Instructions

**Triggered by:** orchestrator inline after `append_turns.py` outputs `CONDENSE_NEEDED`
**Model:** `claude-sonnet-4-6`

You are given a `dialogue_id`. Execute the condensing pass completely.

> **Overwrite check:** The orchestrator already probed for `application/dialogue/condense_memory.overwrite.md` and listed it in the prompt's Required reads block (if present) or absent_confirmed block (if not). Trust those lists — do not Glob or Bash-stat for it yourself.

> **Input contract:** Required reads in the prompt is the COMPLETE list of files for this spawn. The condense_cache.json is your single self-contained input — do not Read, Glob, or Bash-stat any other path.

---

## 1. Read scene data

Read a single file:

- `infrastructure/dialogues/{dialogue_id}/condense_cache.json` — pre-built by the orchestrator's prep script. Contains everything you need:
  - `batch` — the turns to condense (from `condensed_through` to end of `full_chat`)
  - `batch_range` — `[start_index, end_index]`
  - `full_chat_len` — total turns in full_chat
  - `condensed_through` — where prior memory ends
  - `existing_memory` — current `memory.json` contents (or null if first condense)
  - `recent_chat` — current context window (for `short_memory`)
  - `participants` — per-character `{ name, core_traits, emotional_baseline }`
  - `scenario_summary` — leading character's scenario text

Do NOT read `full_chat.json`, `memory.json`, `recent_chat.json`, `characters.json`, `scenario.json`, or character `data.json` files directly — the cache already contains everything extracted from them.

---

## 2. Save checkpoint

Before writing anything else, save a checkpoint so rollback can restore the pre-condensing state.

Write `infrastructure/dialogues/{dialogue_id}/memory_checkpoint.json`:

```json
{
  "condensed_at": <len(full_chat)>,
  "memory": <current contents of memory.json, or {} if it didn't exist>
}
```

`condensed_at` is the total number of entries in `full_chat.json` at the time of this pass.

---

## 3. Update full memory (`memory.json`)

**Before writing:** Read `infrastructure/dialogues/{dialogue_id}/memory.json` first (it may or may not exist — that's fine). The Write tool requires a prior Read on the path.

Synthesize the existing memory (if any) with the 10-entry condensing batch. Write the result to `infrastructure/dialogues/{dialogue_id}/memory.json`.

The full memory is a cumulative record. It grows over time but stays synthesized — no raw dialogue, only extracted facts and states.

**Schema:**

```json
{
  "condensed_through": <len(full_chat)>,
  "scene_state": "<current location, mood, physical environment>",
  "relationship": "<how the characters relate to each other at this point in the scene>",
  "characters": {
    "<char_id>": {
      "arc": "<emotional/physical arc so far — what has changed for them>",
      "current_state": "<their state at the end of the condensed batch>",
      "key_facts": ["<anything important about them that should persist>"]
    }
  },
  "events": ["<significant events in chronological order, brief>"]
}
```

Rules:
- Merge `events` from existing memory with new events from the batch — do not discard old events
- Update `characters[*].arc` and `current_state` to reflect the end of the condensing batch
- Update `scene_state` and `relationship` based on the batch
- Keep entries concise — this is a lookup, not a narrative

---

## 4. Generate short memory (`short_memory.json`)

**Before writing:** Read `infrastructure/dialogues/{dialogue_id}/short_memory.json` first (it may or may not exist — that's fine). The Write tool requires a prior Read on the path.

Fully rewrite `infrastructure/dialogues/{dialogue_id}/short_memory.json` from `recent_chat.json`. This is a snapshot of the immediate present — what a reader would need to know to walk into the scene right now.

**Schema:**

```json
{
  "generated_from_turn_count": <len(recent_chat)>,
  "scene_now": "<where they are, what's happening right now, immediate physical context>",
  "characters": {
    "<char_id>": {
      "physical_state": "<body, positioning, what they're doing>",
      "emotional_state": "<mood, tension, what they're feeling>"
    }
  },
  "last_beat": "<one-sentence summary of what just happened in the most recent exchange>"
}
```

Rules:
- Derived entirely from `recent_chat.json` — do not import events from outside the context window
- Keep it tight — this is immediate context, not history

---

## 5. Done

No queue item to clear. The orchestrator triggered this inline.
