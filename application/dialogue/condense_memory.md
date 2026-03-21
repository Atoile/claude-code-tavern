# condense_memory — Sonnet Agent Instructions

**Triggered by:** orchestrator inline after `append_turns.py` outputs `CONDENSE_NEEDED`
**Model:** `claude-sonnet-4-6`

You are given a `dialogue_id`. Execute the condensing pass completely.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/condense_memory.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

---

## 1. Read scene data

Read the following files:

- `infrastructure/dialogues/{dialogue_id}/full_chat.json` — take the **last 10 entries** as the condensing batch (the turns that triggered this pass)
- `infrastructure/dialogues/{dialogue_id}/memory.json` — existing cumulative memory (may not exist; treat as empty if absent)
- `infrastructure/dialogues/{dialogue_id}/recent_chat.json` — current context window (used for `short_memory`)
- `infrastructure/dialogues/{dialogue_id}/scenario.json` — scene premise (for grounding)
- Character `data.json` for each character — **identity** (`name`) and **personality** (`core_traits`, `emotional_baseline`) only

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
