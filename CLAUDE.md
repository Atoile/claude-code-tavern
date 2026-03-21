# Tavern Tool

Character interaction tool — Claude orchestrates dialogue **between** characters while the user directs. Prototype for RPG conversation system.

## Architecture

```
Web App (Svelte + Vite)          Claude Code (manual trigger)
        │                                │
        ├─ writes queue.json ───────────►├─ reads queue.json (FIFO)
        ├─ pauses UI                     ├─ routes tasks by type
        ├─ watches queue.json            ├─ calls Haiku/Sonnet via API
        │                                ├─ calls Python scripts (TTS/SDXL)
        └─ unpauses when queue empty ◄───└─ writes results, clears queue
```

- **No backend server.** App is pure frontend + local storage.
- **Claude Code is the sole queue processor.** Triggered manually by the user.
- **Python CLI scripts** for local GPU tasks (XTTS v2, Whisper, SDXL) — invoked by Claude Code via shell.

## Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | Svelte + Vite | Lightweight reactive UI |
| Storage | Local filesystem + localStorage | No database |
| LLM orchestration | Claude Code → Haiku/Sonnet API | Haiku orchestrates, Sonnet creates |
| TTS | XTTS v2 (local, 5070Ti) | Python CLI script |
| Speech validation | Whisper (local) | Python CLI script |
| Image gen | SDXL (local, 5070Ti) | Python CLI script |
| Image validation | Gemini Flash (free tier) | Deferred — not yet integrated |

## Model Assignment

| Task | Model |
|------|-------|
| Dialogue generation | Sonnet |
| Scene direction interpretation | Sonnet |
| Character card repacking | Sonnet |
| Queue orchestration | Haiku |
| SDXL prompt generation | Haiku |
| Voice archetype assignment | Haiku |

Use `claude-sonnet-4-6` for Sonnet tasks, `claude-haiku-4-5-20251001` for Haiku tasks.

## Directory Structure

```
tavern/
├── CLAUDE.md
├── domain/                         # Pure domain knowledge — no layer owns this
│   ├── character/
│   │   └── schema.md               # Character aggregate schema and field contracts
│   └── dialogue/
│       ├── writing_rules.md        # Formatting rules for all dialogue output
│       └── scene_structure.md      # Dialogue session file contracts
├── application/                    # Application services — agent instructions per task type
│   ├── character/
│   │   └── repack.md
│   ├── dialogue/
│   │   ├── optimize_scenario.md
│   │   └── generate_reply.md
│   └── scripts/                    # Python CLI scripts for local GPU tasks
│       ├── card_extract.py         # Extract JSON + avatar from SillyTavern PNGs
│       ├── tts_generate.py         # XTTS v2 TTS generation
│       ├── tts_validate.py         # Whisper transcription check
│       ├── sdxl_generate.py        # SDXL portrait generation
│       └── sdxl_validate.py        # Gemini Flash portrait validation (deferred)
├── infrastructure/                 # Repository implementations and data stores
│   ├── characters/
│   │   └── {id}/
│   │       └── data.json           # Repacked character data
│   ├── dialogues/
│   │   └── {id}/
│   │       ├── characters.json     # Characters in this scene
│   │       ├── scenario.json       # Scene setting and direction
│   │       ├── memory.json         # General scene memory (optional)
│   │       ├── recent_chat.json    # Recent dialogue rounds (context window)
│   │       └── full_chat.json      # Complete dialogue history
│   ├── queue/
│   │   └── queue.json              # Task queue (FIFO, self-contained items)
│   └── raw/                        # Imported SillyTavern card PNGs (source files)
├── src/                            # Svelte app source (presentation layer)
└── public/                         # Static assets
```

## Queue Format

Each item in `queue.json` is self-contained:

```json
{
  "id": "uuid",
  "type": "see task types below",
  "parallel": false,
  "depends_on": [],
  "model": "sonnet | haiku",
  "input": {},
  "output_path": "path/to/write/result",
  "status": "pending | processing | done | error"
}
```

Processing: read FIFO → respect `depends_on` ordering → set `processing` → execute → write result to `output_path` → remove from queue.

### Task Types

| Type | Model | Description |
|------|-------|-------------|
| `repack_character` | Sonnet | Extract + synthesize SillyTavern card into `data.json` |
| `optimize_scenario` | Sonnet | Generate interaction scenario tailored to two specific characters |
| `optimize_opening` | Sonnet | Adapt selected greeting from user-facing to character-to-character framing |
| `write_opening_line` | Sonnet | Commit leading character's opening line to dialogue files |
| `generate_reply` | Sonnet | Generate next dialogue round from one or both characters |
| `sdxl_prompt` | Haiku | Generate SDXL image prompt from character appearance data |
| `tts_generate` | — | Shell out to `application/scripts/tts_generate.py` (XTTS v2) |
| `tts_validate` | — | Shell out to `application/scripts/tts_validate.py` (Whisper) |

## Character Card Repacking

Import flow: raw PNG → extract embedded JSON → Sonnet synthesizes → write to `infrastructure/characters/{id}/data.json`.

Repacked structure:
- Core personality traits (normalized)
- Speech patterns and vocabulary tendencies
- Relationship defaults and behavioral tendencies
- Voice archetype assignment
- Physical description (normalized for portrait generation)
- Magic/ability summary if relevant

## Voice Archetypes

Dimensions: role × personality axis × age tier.
- **Role:** warrior, scholar, clergy, merchant, noble, commoner
- **Personality:** dominant/submissive, warm/cold, serious/playful
- **Age:** young, mature, elder

One XTTS v2 voice model per archetype, not per character. Auto-assigned by Haiku on import, user can override in UI.

## UI Design

Mobile chat-inspired layout:
- Character avatars from card PNG
- Left/right alignment per character, distinct colors
- Scene context at top
- Dedicated character settings panel (voice audition, portrait, archetype tags)
- Round-based: user prompts for next round, can delete last round without LLM

## Chat Initialization Workflow

### Character Selection (UI)

Characters list distinguishes **repacked** vs **raw** — two separate lists. A character cannot appear on both. User selects two characters (from either list).

---

### Stage 1 — Scene Setup (queue → Claude Code → queue empty → UI unpauses)

**If either character is raw**, queue items (parallel where noted):
```
repack_character { char: A }   ← parallel
repack_character { char: B }   ← parallel
optimize_scenario { char_a: A, char_b: B }   ← depends on both repacks
```

**If both already repacked**, queue:
```
optimize_scenario { char_a: A, char_b: B }
```

`optimize_scenario` — Sonnet reads both characters' `data.json` and writes a scenario tailored to their interaction into `infrastructure/dialogues/{id}/scenario.json`. It also suggests 2-3 starting dialogue options derived from the leading character's `dialogue_seeds`.

After queue clears, UI shows:
- The optimized scenario
- Prompt to select **leading character** (displayed on right side of chat)
- Starting dialogue options to pick from

---

### Stage 2 — Dialogue Initialization (queue → Claude Code → queue empty → UI enters chat)

After user selects leading character and starting dialogue, queue:
```
optimize_opening { dialogue_id, leading_char, selected_greeting }
write_opening_line { dialogue_id, leading_char }
generate_reply { dialogue_id, replying_char }
```

- `optimize_opening` — Sonnet adapts the selected greeting from user-facing to character-to-character framing, writes to `infrastructure/dialogues/{id}/full_chat.json` and `recent_chat.json`
- `write_opening_line` — final leading character line committed
- `generate_reply` — second character's first reply generated and appended

---

### Stage 3 — In-Dialogue Actions

| Action | Queue items | Notes |
|--------|-------------|-------|
| **Continue** | `generate_reply { both chars }` | Both characters reply as they see fit |
| **Continue with direction** | `generate_reply { both chars, user_prompt }` | User's steering prompt included |
| **Rollback** | *(no queue)* | Remove last round from `recent_chat.json` and `full_chat.json` |
| **Reset dialogue** | `generate_reply { replying_char }` | Clears everything after first opening line, regenerates first reply |

---

### Queue Item Dependencies

Items within a stage that depend on previous results must be queued sequentially. Items with no dependency on each other can be marked `parallel: true` and processed concurrently.

```json
{
  "id": "uuid",
  "type": "task_type",
  "parallel": true,
  "depends_on": ["uuid-of-prior-task"],
  "model": "sonnet | haiku",
  "input": {},
  "output_path": "path/to/result",
  "status": "pending | processing | done | error"
}
```

---

## Running the Queue

When the user says **"run queue"** (or similar — "process queue", "go", etc.), Claude Code orchestrates directly:

### Steps

1. **Read** `infrastructure/queue/queue.json`
2. **Find the next eligible task** — `status` is `pending` and every ID in `depends_on` has `status: done` (or `depends_on` is empty). Pick the first in array order.
3. **Route** by task type:

| Task type | Agent instructions file |
|---|---|
| `repack_character` | `application/character/repack.md` |
| `optimize_scenario` | `application/dialogue/optimize_scenario.md` |
| `generate_reply` | `application/dialogue/generate_reply.md` |

4. If the task type is not in the table: output `ERROR: no agent defined for task type "<type>". Queue stopped.` and stop.
5. **Spawn a general-purpose subagent** with this prompt:
   ```
   Read your instructions from <AGENT_FILE> and execute the task.

   Task input (exact queue item):
   <TASK_JSON>

   Working directory is the repository root.
   ```
6. **After the task agent finishes**, re-read `infrastructure/queue/queue.json`. If no eligible pending tasks remain, remove all `status: done` items and write the file back.

## Key Principles

- **Each scene starts fresh** — no cross-session memory
- **User is director, not participant** — dialogue is between characters
- **Queue is the only interface between app and Claude Code**
- **Gemini integration deferred** — do not implement yet

## Overwrite System

Agent instruction files and domain documents ship as SFW baselines. Any file can be extended with an adjacent `*.overwrite.md` file:

```
application/character/repack.md           ← baseline
application/character/repack.overwrite.md ← user extension (gitignored)
```

**How it works:**
- Each agent instruction file contains an overwrite check near the top — it tells the subagent to look for its `.overwrite.md` counterpart before proceeding.
- If the overwrite file exists, the agent reads it and merges the additional rules into its execution. Overwrite rules take precedence where they conflict with the baseline.
- If the overwrite file does not exist, the agent proceeds with the baseline only.

**Gitignore:** `*.overwrite.md` is excluded from version control. Users create and manage their own overwrite files locally.

**Scope:** Any agent or domain file can have an overwrite counterpart. The naming convention is always `<original-filename>.overwrite.md` in the same directory.
