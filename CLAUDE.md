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
| TTS | Kokoro (default) / XTTS v2 | API or Python CLI script; engine set via `VITE_VOICE_ENGINE` |
| Speech validation | Whisper (local) | Python CLI script |
| Image gen | SDXL (local, 5070Ti) | Python CLI script |
| Image validation | Gemini Flash (free tier) | Deferred — not yet integrated |

## Model Assignment

| Task | Model |
|------|-------|
| Dialogue generation | Sonnet |
| Scene direction interpretation | Sonnet |
| Character card repacking | Sonnet |
| Queue orchestration | Sonnet |
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
| `optimize_scenario` | Sonnet | Generate interaction scenario tailored to the scene's participant set (2 or more characters) |
| `generate_reply` | Sonnet | Generate the next dialogue round — variable-length turn list, planner picks who speaks |
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

**SVG conventions:** Inline SVGs must use `style="fill: none"` instead of `fill="none"` — the Svelte language server flags `fill` as an obsolete HTML attribute. All other SVG presentation attributes (`stroke`, `stroke-width`, `stroke-linecap`, `stroke-linejoin`) are fine as-is.

Mobile chat-inspired layout:
- Character avatars from card PNG
- Left/right alignment per character, distinct colors
- Scene context at top
- Dedicated character settings panel (voice audition, portrait, archetype tags)
- Round-based: user prompts for next round, can delete last round without LLM

## Chat Initialization Workflow

### Character Selection (UI)

Characters list distinguishes **repacked** vs **raw** — two separate lists. A character cannot appear on both. The user selects **2 or more characters** (currently capped at 4) from either list to start a scene.

---

### Stage 1 — Scene Setup (queue → Claude Code → queue empty → UI unpauses)

For each raw character in the selection, the frontend queues a `repack_character` task (parallel). After all repacks complete, it queues a single `optimize_scenario`:
```
repack_character { char: A }   ← parallel
repack_character { char: B }   ← parallel (one per raw participant)
optimize_scenario { participants: [A, B, ...] }   ← depends on all repacks
```

`optimize_scenario` — Sonnet reads every participant's `data.json` and writes a scenario tailored to their interaction into `infrastructure/dialogues/{id}/scenario.json`. The output is a participant-id-keyed dict with one entry per character, each containing an adapted scenario and the character's adapted greetings (one per source line).

After queue clears, UI shows:
- The optimized scenario
- Prompt to select **leading character** (displayed on right side of chat)
- Starting dialogue options to pick from

---

### Stage 2 — Dialogue Initialization (frontend writes directly, then navigates immediately)

After user selects the leading character and starting greeting, the frontend:

1. Writes the opening line directly into `full_chat.json` and `recent_chat.json` via the dev-server REST endpoints (no queue task).
2. Updates `characters.json` with `leading_id`.
3. Queues a single `generate_reply { dialogue_id, leading_char_id }` task as a normal reply (identical shape to every subsequent Continue).
4. **Navigates to the dialogue view immediately** — no pause for queue completion. The opening line is already visible; the background queue item fills in the reply when it finishes. The dialogue panel's existing queue watcher handles the progress indicator.

There is no "first-turn mode." The opening line is just another entry in `recent_chat.json`, and the planner treats it exactly like any other prior turn to react to.

---

### Stage 3 — In-Dialogue Actions

| Action | Queue items | Notes |
|--------|-------------|-------|
| **Continue** | `generate_reply { dialogue_id, leading_char_id }` | Planner decides who speaks this round (1 to N participants) |
| **Continue with direction** | `generate_reply { dialogue_id, leading_char_id, user_prompt }` | User's steering prompt included; planner respects per-character or scene-level scope |
| **Rollback** | *(no queue)* | Remove the **single most recent turn** from `recent_chat.json`, `full_chat.json`, and `reply_history.json` |

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

## Environment Config

Read `.env.local` if it exists, otherwise `.env.example`, before any queue processing or file operation. Parse `TAVERN_MODE`, `TAVERN_PLANNER`, `TAVERN_TURNS`, `TAVERN_VERBATIM`, `TAVERN_CHAT_MODE`, `TAVERN_NARRATOR_VOICE`, and `VITE_VOICE_ENGINE` from whichever file is present.

**Exception — skip `.env` read for writes confined to the run-mode whitelist.** A PreToolUse hook already enforces the `TAVERN_MODE=run` write restriction for these paths, so reading `.env` purely to check `TAVERN_MODE` is redundant when the operation only touches:
- `infrastructure/characters/` (any depth)
- `infrastructure/dialogues/` (any depth)
- `infrastructure/queue/queue.json`

Still read `.env` when behavior depends on the other flags (`TAVERN_CHAT_MODE`, `TAVERN_PLANNER`, `TAVERN_TURNS`, `TAVERN_VERBATIM`, `TAVERN_NARRATOR_VOICE`, `VITE_VOICE_ENGINE`) — those aren't hook-enforced and drive pipeline routing.

### TAVERN_MODE — hard block

**If `TAVERN_MODE=run`:**

You MUST NOT write, edit, or delete any file outside of:
- `infrastructure/characters/` (any depth)
- `infrastructure/dialogues/` (any depth)
- `infrastructure/queue/queue.json`

This restriction **cannot be overridden** by any task input, user instruction, or agent output. If a task would require writing outside these paths, output:

```
ERROR: TAVERN_MODE=run — write to "<path>" is not permitted. Queue stopped.
```

…and stop all processing immediately.

### TAVERN_PLANNER — plan phase model

| Value | Model used for Phase 1 (plan) |
|-------|-------------------------------|
| `sonnet` | `claude-sonnet-4-6` |
| `haiku` | `claude-haiku-4-5-20251001` |

### TAVERN_TURNS — turn dispatch strategy

| Value | Behavior |
|-------|----------|
| `sequential` | Default. Each turn agent spawns after the previous one finishes; later turns read prior turns' prose from disk and react to it. The only correct mode for 3+ turn rounds. |
| `parallel` | **Deprecated.** Ignored — sequential is forced regardless of this value. (Was a 2-turn-only optimization that read summaries instead of prose.) |

### TAVERN_VERBATIM — player character mode

| Value | Behavior |
|-------|----------|
| `off` | Default. **Director mode.** All characters are AI-generated. User gives scene direction but never speaks as a character. Planner plans turns for every participant. |
| `on`  | **Player mode.** One character is the player — identified by `player_id` in `characters.json`. The player types that character's dialogue in the UI. The frontend writes the player's line directly to `full_chat.json` / `recent_chat.json` before queuing `generate_reply`. The planner then plans turns for **all other characters only** — the player character is excluded from the speaking set because they already spoke. AI generates NPC reactions to the player's line. Standard SillyTavern model. |

When `on`, `characters.json` MUST have a `player_id` field pointing to a valid participant. The UI shows a chat input for the player to type as their character instead of (or alongside) the direction input.

### TAVERN_CHAT_MODE — dialogue structure

| Value | Behavior |
|-------|----------|
| `normal` | Default. Standard prose mode — characters write full turns combining speech + actions in first person. Fixed-length rounds (each character speaks once per round). Uses `generate_reply_plan.md` and `generate_reply_turn.md`. |
| `narrator` | Narrator mode — characters ONLY speak (quoted dialogue), a neutral narrator handles all physical actions/descriptions in third person. Variable-length rounds: NPCs converse freely until player input is needed. Uses `generate_reply_plan_narrator.md`, `expand_character_narrator.md` (speech), and `expand_round_narrator.md` (narration). Goals replace scenarios as scene anchors — reads `goals.json` instead of `scenario.json`. |

**Mid-dialogue mode transitions:** Switching `TAVERN_CHAT_MODE` between rounds is supported. The `generate_reply` pipeline detects mismatches (e.g. dialogue started as `narrator` but env now says `normal`) and bridges automatically — see Phase 0b in the pipeline docs. Currently supported: `narrator → normal`. The reverse (`normal → narrator`) is not yet implemented.

### TAVERN_NARRATOR_VOICE — narrator register (only when `TAVERN_CHAT_MODE=narrator`)

| Value | Behavior |
|-------|----------|
| `neutral` | Default. Clean, transparent, minimal. Present tense. Reports what happens without style. |
| `literary` | Slightly more descriptive, atmospheric. Past tense allowed. Adapts to scene mood. |

### VITE_VOICE_ENGINE — TTS routing

| Value | Behavior |
|-------|----------|
| `off` | Skip all `tts_generate` and `tts_validate` tasks |
| `kokoro` | Route TTS tasks to Kokoro API at `VITE_VOICE_ENGINE_URL` |
| `xtts` | Route TTS tasks to XTTS v2 script/API at `VITE_VOICE_ENGINE_URL` |

---

## Running the Queue

When the user says **"run queue"** (or similar — "process queue", "go", etc.), Claude Code orchestrates directly:

### Steps

0. **Overwrite check:** Before doing anything else, check whether `CLAUDE.overwrite.md` exists in the project root. If it does, read it — its contents extend these baseline instructions and take precedence where they conflict.

1. **Read env config fresh** — re-read `.env.local` (or `.env.example` if absent) at the start of **each queue run**, even if it was read earlier in the same session. The user may have changed flags between runs. Do not reuse a cached read. Then **read** `infrastructure/queue/queue.json`.
2. **Find the next eligible task** — `status` is `pending` and every ID in `depends_on` has `status: done` (or `depends_on` is empty). Pick the first in array order.
3. **Route** by task type:

| Task type | Agent instructions file |
|---|---|
| `repack_character` | `application/character/repack.md` |
| `optimize_scenario` | `application/dialogue/optimize_scenario.md` |
| `generate_reply` | 4-phase pipeline (see step 4a) |
| `condense_memory` | `application/dialogue/condense_memory.md` — triggered inline, not queued (see step 6) |

4. If the task type is not in the table: output `ERROR: no agent defined for task type "<type>". Queue stopped.` and stop.

4a. **For `generate_reply` tasks — 4-phase pipeline (Plan → Validate → Turns → Merge/Append):**

   **Phase 0 — Prep scripts:** Run all five before anything else, in this order:
   ```
   python application/scripts/build_writing_rules_cache.py
   python application/scripts/build_context_cache.py --dialogue-id {input.dialogue_id}
   python application/scripts/extract_prose_tail.py --dialogue-id {input.dialogue_id}
   python application/scripts/extract_last_turn.py --dialogue-id {input.dialogue_id}
   python application/scripts/build_active_lorebook.py --dialogue-id {input.dialogue_id} [--user-prompt "{input.user_prompt}"]
   ```
   All scripts are safe to run every time — they skip or overwrite cleanly. `extract_prose_tail.py` writes the last 2 turns (truncated to ~500 chars) into `prose_tail.json` for voice matching. `extract_last_turn.py` writes the single last turn from the prior round (full text) into `last_turn.json` so turn 0 of this round knows exactly what it is reacting to. `build_active_lorebook.py` must run **after** `extract_prose_tail.py` and `extract_last_turn.py` because it reads both to build the keyword haystack. Pass `--user-prompt` only when `input.user_prompt` is present in the task input. The script writes `active_lorebook.json` — a per-character dict of lore entries selected by four criteria (always / pattern / cross-character name / haystack keyword), replacing the old baked-into-`context_cache.json` lore slice.

   **Phase 0b — Mode Transition (narrator → normal):**

   Check whether a mode transition is needed:
   - Read `infrastructure/dialogues/{dialogue_id}/characters.json`
   - If `TAVERN_CHAT_MODE=normal` AND `characters.json` has `"narrator": true`:

   **This dialogue was started in narrator mode but the env now says normal.** The normal-mode planner needs `scenario.json` as its scene anchor, but narrator-mode dialogues use `goals.json` instead. Generate a bridge scenario.

   1. Read `goals.json` to determine goal status (active vs resolved).
   2. Read `recent_chat.json` (last 4-6 turns) for current scene state.
   3. Read each participant's `context_cache_{char_id}.json` for character data.

   4. Spawn a **Sonnet** subagent to generate `infrastructure/dialogues/{dialogue_id}/scenario.json`:

      ```
      You are generating a scenario.json to bridge a narrator→normal mode transition mid-dialogue.

      Dialogue ID: {dialogue_id}

      Read the following files:
      - goals.json: infrastructure/dialogues/{dialogue_id}/goals.json
      - recent_chat.json: infrastructure/dialogues/{dialogue_id}/recent_chat.json (last 4-6 turns for current state)
      - Character caches: infrastructure/dialogues/{dialogue_id}/context_cache_{char_id}.json (one per participant)

      Goal status: {active | resolved}
      {If resolved: goal_id, outcome, and detail from complete.json or goals.json resolved_as}

      Write scenario.json with this schema:
      {
        "dialogue_id": "{dialogue_id}",
        "generated_at": "<ISO 8601 now>",
        "mode_transition": true,
        "transitioned_from": "narrator",
        "participants": {
          "<char_id>": {
            "name": "<display name>",
            "scenario": "<1-3 paragraphs, first-person POV from this character — describes the scene AS IT IS RIGHT NOW based on recent_chat, not the original greeting>",
            "openings": []
          }
        }
      }

      Rules:
      - `openings` is empty — we are mid-dialogue, past the opening. This is valid.
      - `scenario` must reflect the CURRENT scene state from recent_chat, not the original greeting or goals description.
      - If goals are ACTIVE: scenario picks up the current beat. Each character's scenario describes where they are, what just happened, their emotional state, and the unresolved tension driving the scene forward. The goal's intent carries into the scenario naturally.
      - If goals are COMPLETED: scenario reflects the resolution. Each character's scenario describes the aftermath — the new dynamic, the shifted relationship, what happens next. The resolved goal's outcome shapes the framing.
      - Use each character's voice and POV for their scenario entry — write as if the character is narrating their own current situation.
      - Physical details (location, clothing, posture, objects) must match what recent_chat established. Do not revert to card defaults if the prose contradicts them.

      Working directory is the repository root.
      ```

   5. After the agent writes `scenario.json`, read it and present a brief summary to the user:
      - Show each participant's scenario (first 2 sentences each)
      - **Mismatch check:** If any scenario entry contradicts recent chat (wrong location, wrong emotional state, wrong physical details), flag it explicitly and ask the user to confirm or correct before proceeding.
      - If it looks clean, note the transition and continue.

   6. Update `characters.json`: set `"narrator"` to `false`.
   7. Re-run `python application/scripts/build_context_cache.py --dialogue-id {dialogue_id}` to pick up the new scenario. This overwrites the prior context cache that had no scenario data.

   If `TAVERN_CHAT_MODE=normal` and `characters.json` does NOT have `"narrator": true`, skip this phase entirely — no transition needed.

   If `TAVERN_CHAT_MODE=narrator`, skip this phase entirely — no transition needed regardless of `characters.json` state.

   **Phase 1 — Plan:** Spawn a general-purpose subagent using the model set by `TAVERN_PLANNER` (`sonnet` → `claude-sonnet-4-6`, `haiku` → `claude-haiku-4-5-20251001`). The planner instruction file depends on `TAVERN_CHAT_MODE`:
   - `normal` → `application/dialogue/generate_reply_plan.md`
   - `narrator` → `application/dialogue/generate_reply_plan_narrator.md`

   ```
   Read your instructions from <PLANNER_FILE> and execute the task.

   Task input (exact queue item):
   <TASK_JSON>

   Working directory is the repository root.
   ```
   Wait for it to finish. It writes `infrastructure/dialogues/{dialogue_id}/reply_plan.json` with a variable-length `turns[]` array — the planner picks who speaks this round (1 to N participants).

   **Phase 1b — Validate plan:** Spawn a general-purpose subagent (use `haiku` model):
   ```
   Read your instructions from application/dialogue/validate_plan.md and execute the task.

   Dialogue ID: {input.dialogue_id}

   Task input (exact queue item):
   <TASK_JSON>

   Working directory is the repository root.
   ```
   Wait for it to finish. It writes `infrastructure/dialogues/{dialogue_id}/plan_validation.json`.

   Read `plan_validation.json`. If `status` is `"pass"`, continue to Phase 2. Log any warnings to the user but do not stop.

   If `status` is `"fail"`, route to the handler (Phase 1c).

   **Phase 1c — Handle validation failure:**

   The handler is **gated by check-ID coverage**. Read `application/dialogue/handle_plan_validation.md` and collect every check ID that has an established entry under the **"Known issue handling rules"** section (each rule declares its `check ID` in the `###` header). Then inspect every issue in `plan_validation.json.issues` and collect their `check` IDs.

   - **All failing check IDs are established** → spawn the handler (established-runtime path below).
   - **Any failing check ID is not established** → interim hard-stop (unestablished-runtime path below). The handler cannot safely classify what it has no rule for, so surface it to the user first.

   *Established runtime:* Spawn a Sonnet handler agent using `application/dialogue/handle_plan_validation.md`. The handler classifies each issue, then:
   - **Critical issues** → handler deletes `reply_plan.json` + `plan_validation.json`, writes `handler_result.json` with `status: "restart"`. The orchestrator returns to Phase 1 (replan from scratch).
   - **Fixable issues** → handler patches `reply_plan.json` in place, runs `check_beat_sizing.py` to verify, deletes the old `plan_validation.json`, writes `handler_result.json` with `status: "patched"` and a `revalidation_needed` boolean. Routing depends on the flag:
     - `revalidation_needed: true` (any structural patch — split, weight bump, extract-to-new-beat, mixed) → orchestrator returns to Phase 1b (re-run validator against the patched plan).
     - `revalidation_needed: false` (trim-only patches, sizing tool confirmed PASS) → orchestrator skips Phase 1b and proceeds directly to Phase 2. Pure trims cannot regress any non-sizing check, and the sizing tool has already verified the only thing a trim could break.

   *Unestablished runtime (interim — only when at least one failing check ID has no rule yet):* Hard-stop the pipeline. Do NOT proceed to Phase 2. Do NOT spawn the handler agent. Instead:

   1. Report the failing issues to the user concisely (one line per issue: check ID, severity, speaker, detail). Flag which check IDs are unestablished.
   2. Ask the user how this kind of failure should be handled (critical → restart plan, or fixable → specify the patch rule).
   3. After the user answers, append the new rule into `application/dialogue/handle_plan_validation.md` under the **"Known issue handling rules"** section. Use this format for each rule:
      ```
      ### <check ID> — <one-line title>
      **Classification:** critical | fixable
      **Trigger:** <which detail patterns match this rule>
      **Action:** <exact patch instruction, or "restart plan phase">
      ```
   4. Stop the pipeline. The user decides whether to re-run the queue manually. The newly-established rule will route through the handler on next encounter.

   **Phase 2 — Generate turns sequentially:**

   **Note on `apply_verbatim.py`:** This script is parked and not invoked by the current pipeline. It was designed for a future scripted-insert feature. `TAVERN_VERBATIM` now controls player character mode (see env config above), which does not use this script — the player's line is written to the chat by the frontend before the pipeline runs, so no plan-side verbatim materialisation is needed. Skip this call entirely regardless of the flag value.

   Then read `reply_plan.json` to learn the turn count `N = len(turns)`.

   **Build turn context caches** (normal mode only — narrator mode uses its own routing):
   ```
   python application/scripts/build_turn_context.py --dialogue-id {input.dialogue_id}
   ```
   This writes `turn_context_{i}.json` per turn, collapsing plan, briefs, lorebook, writing rules, and prose tail into one file per agent. Eliminates token pyramiding from sequential tool reads.

   **For each turn index `i` from 0 to N-1, in order:**

   1. **Only when `TAVERN_VERBATIM=on`:** if `reply_turn_{i}.json` already exists on disk (because `apply_verbatim.py` materialized it), skip the agent spawn and proceed to step 3. When the flag is off, skip this check — proceed directly to step 2.
   2. Spawn one `generate_reply_turn` subagent (see prompt below). Wait for it to finish — it writes `infrastructure/dialogues/{input.dialogue_id}/reply_turn_{i}.json`.
   3. Run `python application/scripts/preview_turn.py --dialogue-id {input.dialogue_id}` to refresh the UI preview. This script idempotently rebuilds `preview_turn.json` from whatever `reply_turn_*.json` files exist on disk, so the UI can display each new turn the moment it lands.

   After the loop completes, every entry in `reply_plan.turns[]` has a matching `reply_turn_{i}.json` on disk and the pipeline can proceed to merge.

   **Sequential is mandatory.** `TAVERN_TURNS=parallel` is deprecated and ignored — turns must always be generated in order so each turn agent can read the actual prose of every prior turn this round.

   **Prompt convention:** Agent prompts should reference files by **path**, not by inlined contents. The orchestrator does NOT pre-read prose files and substitute their contents into prompts — the agent reads its own inputs from disk. The only thing the orchestrator inlines into a prompt is `<TASK_JSON>` (the queue item itself, which is small and the agent's primary input). All other inputs are passed as file paths in a "Required reads" block, and the agent is responsible for reading them.

   **Turn agent prompt** (one per turn `i` in order). The instruction file depends on `TAVERN_CHAT_MODE`:
   - `normal` → `application/dialogue/generate_reply_turn.md` (prose expansion)
   - `narrator` → **fresh-per-turn agents** (Haiku). Each turn spawns a fresh minimal-context Haiku agent. Character agents see ONLY their own character brief — structural voice isolation. No persistent agents, no SendMessage.

     **Step 1 — Split the plan:**
     ```
     python application/scripts/split_plan_by_speaker.py --dialogue-id {input.dialogue_id} --narrator-voice {TAVERN_NARRATOR_VOICE}
     ```
     This writes `plan_slice_{speaker}.json` for each unique speaker + `plan_turn_order.json`.

     **Step 2 — Execute turns with smart routing:**
     Read `plan_turn_order.json` to get the turn sequence. The orchestrator classifies and routes each turn:

     **Verbatim detection:** A character speech turn is **verbatim** when every string in its `beats` array is a complete quoted line — i.e., each beat starts with `\"` and ends with `\"` (escaped quotes in JSON). The orchestrator checks this before deciding whether to spawn an agent.

     **Route A — Verbatim character speech (direct write, zero tokens):**
     If the turn is a character speech turn AND all beats are verbatim quoted dialogue, the orchestrator writes `reply_turn_{i}.json` directly — no agent spawn:
     ```json
     {
       "speaker": "<speaker_id>",
       "type": "speech",
       "text": "<beats joined with \\n\\n>"
     }
     ```
     This is the common case for narrator-mode rounds where the planner writes the exact dialogue. Examples: `"Three."`, `"One down."`, `"Six remaining for me."` — the planner already did all the creative work. Write ALL verbatim turns upfront before spawning any agents.

     **Route B — All narrator turns in a single agent:**
     Narrator turns don't bounce off character speech — they describe physical events the planner already scripted. Spawn **one** Sonnet agent that writes ALL narrator turns for the round in a single call:
     ```
     Read your instructions from application/dialogue/expand_round_narrator.md.

     Dialogue ID: {input.dialogue_id}
     Narrator voice: {TAVERN_NARRATOR_VOICE}

     Write the following narrator turns. For each, expand the beats into third-person narration prose and write to the specified file.

     Turn index {i1}:
     Beats: {reply_plan.turns[i1].beats}
     Tone: {reply_plan.turns[i1].tone}
     Output: infrastructure/dialogues/{input.dialogue_id}/reply_turn_{i1}.json

     Turn index {i2}:
     Beats: {reply_plan.turns[i2].beats}
     Tone: {reply_plan.turns[i2].tone}
     Output: infrastructure/dialogues/{input.dialogue_id}/reply_turn_{i2}.json

     (... repeat for all narrator turns in the round)

     Required reads:
     - Writing rules: domain/dialogue/writing_rules_cache.md

     Working directory is the repository root.
     ```
     One agent, one context load, all narrator turns written. Narrator beats are plan-scripted descriptions — they don't need to read character speech to know what to describe.

     **Route C — Reactive character speech (agent expansion, sequential):**
     If a character speech turn has non-verbatim beats (vague, reactive, or descriptive — e.g. "reacts to what she sees"), spawn a fresh Haiku agent with minimal context:
     ```
     Read your instructions from application/dialogue/expand_character_narrator.md and write turn index {i}.

     You are: {speaker}
     Dialogue ID: {input.dialogue_id}

     Your character brief:
     {character_briefs[speaker] from reply_plan.json — inline the brief, ~500 tokens}

     Your plan slice for this turn:
     {the single turn entry from reply_plan.turns[i] — inline beats, tone, voice_notes}

     Required reads:
     - Writing rules: domain/dialogue/writing_rules_cache.md
     - Prose tail: infrastructure/dialogues/{input.dialogue_id}/prose_tail.json

     Prior turns this round:
     {for each j < i, include: "[{speaker_j}]: {text from reply_turn_j.json}"}

     Working directory is the repository root.
     ```

     **Execution order:**
     1. Write all Route A (verbatim) turns directly — instant, zero tokens
     2. Spawn the single Route B (narrator) agent — writes all narrator turns at once
     3. Spawn Route C (reactive) agents sequentially if any exist — these need prior turn context
     4. After all turns are on disk, run `python application/scripts/preview_turn.py --dialogue-id {input.dialogue_id}` once

     After all turns complete, proceed to merge.

     **Cleanup:** After merge, run `python application/scripts/cleanup_round.py --dialogue-id {input.dialogue_id}` to remove remaining intermediates (`turn_context_*.json`, `plan_validation.json`, `last_turn.json`). Merge already deletes `reply_plan.json`, `reply_turn_*.json`, and `plan_slice_*.json`.

   ```
   Read your instructions from <TURN_AGENT_FILE> and execute the task.

   Turn index: {i}
   Speaker:    {reply_plan.turns[i].speaker}

   Task input (exact queue item):
   <TASK_JSON>

   Required reads (read these files yourself):
   - Turn context: infrastructure/dialogues/{input.dialogue_id}/turn_context_{i}.json  (plan turn, brief, lorebook, writing rules, prose tail — all in one file)
   {if i == 0}
   - Last turn:    infrastructure/dialogues/{input.dialogue_id}/last_turn.json   (last turn from the previous round, full text — what you are reacting to)
   {else, for each j in 0..i-1}
   - Prior turn:   infrastructure/dialogues/{input.dialogue_id}/reply_turn_{j}.json  (the turn at index {j} this round, full text)
   {/if}

   Working directory is the repository root.
   ```

   The orchestrator substitutes the appropriate "Required reads" lines based on `i`. Turn 0 reads `turn_context_{i}.json` + `last_turn.json`; turns 1..N-1 read `turn_context_{i}.json` + every prior `reply_turn_{j}.json`.

   **Phase 3 — Merge:** Run the merge script first, on its own:

   ```
   python application/scripts/merge_reply.py --dialogue-id {input.dialogue_id} --output-path {output_path}
   ```

   Merge is fast (sub-second) and writes the canonical post-round artifact `pending_turns.json` (the file at `{output_path}`) while deleting all `reply_turn_*.json` intermediates. Wait for it to finish.

   **Phase 3b/3c/etc — additional Phase 3 agents:** If `CLAUDE.overwrite.md` defines additional Phase 3 agents (e.g. state actualization), launch them **after** merge has finished, in a single parallel tool call. They read their inputs from post-merge artifacts (`pending_turns.json`, `turn_state.json`, etc.) — not from the deleted intermediates. They are self-contained: the prompt tells them which file to read; they read it themselves. The orchestrator does not pre-read or inline prose contents.

   Wait for all Phase 3 steps to finish.

   **Phase 4 — Append:** Run:
   ```
   python application/scripts/append_turns.py --dialogue-id {input.dialogue_id} --turns-file {output_path} [--user-prompt "{input.user_prompt}"]
   ```
   Include `--user-prompt` only if `input.user_prompt` is present in the task input.
   If `CLAUDE.overwrite.md` defines additional Phase 4 steps, run them sequentially after append.

4b. **For all other task types:** Spawn a general-purpose subagent with:
   ```
   Read your instructions from <AGENT_FILE> and execute the task.

   Task input (exact queue item):
   <TASK_JSON>

   Working directory is the repository root.
   ```

**529 overloaded — inline fallback (Sonnet only):** If spawning any subagent returns a 529 error:

- **If the orchestrator is running on `claude-sonnet-4-6`:** confirm with the user:
  > "API returned 529 (overloaded) spawning the subagent. I'm running on Sonnet and can execute this task directly inline — proceed?"
  If the user confirms, execute the task inline by reading the agent instruction file yourself and performing all steps directly, without spawning a subagent.
- **If the orchestrator is running on any other model** (Opus is overkill for task execution; Haiku lacks the capability): report the 529 to the user and stop. Do not attempt inline execution.

If the user declines inline execution, stop and wait for them to retry.

5. **After the task completes:**
   - For `generate_reply` tasks:
     1. Run `python application/scripts/cleanup_round.py --dialogue-id {dialogue_id}` to remove remaining intermediates.
     2. Check append output for `CONDENSE_NEEDED`.
     3. If the script outputs `CONDENSE_NEEDED {dialogue_id}`, first run the prep script to build the cache:
        ```
        python application/scripts/build_condense_cache.py --dialogue-id {dialogue_id}
        ```
        Then spawn a `condense_memory` subagent using `application/dialogue/condense_memory.md` with the dialogue_id. Do not queue it — run it inline before moving on.
     4. **Goal completion check:** Check append output for `GOAL_COMPLETED`. If present, `append_turns.py` has already written `complete.json` and updated `goals.json` — the orchestrator does not need to write these files. Report to the user: "Dialogue completed — goal '{goal_id}' resolved as '{outcome}'."
   - Set the completed task's `"status"` to `"done"` in the queue (already in memory — agents do not touch `queue.json`) and write it back.
   - If no eligible pending tasks remain, remove all `status: done` items and write the file back.

## Creating a Character from Scratch

When the user asks to **create a new character** (not repack an existing card), read the following files before doing anything else:

1. `domain/character/schema.md` — field contracts and structure
2. `domain/character/schema.overwrite.md` — if it exists
3. `domain/character/template.json` — structural reference with inline guidance
4. `application/character/create_from_scratch.md` — agent instructions and design guidelines
5. `application/character/create_from_scratch.overwrite.md` — if it exists
6. Run `python application/scripts/build_writing_rules_cache.py` to build/refresh `domain/dialogue/writing_rules_cache.md` (merges baseline + `writing_rules.overwrite.md`).
7. `domain/dialogue/writing_rules_cache.md` — the pre-merged prose and formatting rules (dialogue seeds / sample lines must follow these).

All reads (skipping missing overwrites) must complete before prompting the user for design choices or writing any card data.

## Repacking a Raw Card

When the user asks to **repack a raw SillyTavern card** (outside the normal queue flow — e.g. a direct request to repack a specific card), follow the same build step and read the same files listed above in "Creating a Character from Scratch", **plus**:

8. `application/character/repack.md` — repack agent instructions
9. `application/character/repack.overwrite.md` — if it exists

All reads (skipping missing overwrites) must complete before inspecting the raw card or writing any repacked data.

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

## Python Linting

When the user asks to **lint** Python files, use the project lint scripts:

| Request | Command |
|---|---|
| "lint everything", "lint all files" | `python lint_all.py` |
| "lint changed", "lint what I changed" | `python lint_changed.py` |
| specific file / directory | `ruff check <files>` then `pyright <files>` directly |

`lint_all.py` — runs ruff + pyright over every `.py` file tracked by git.
`lint_changed.py` — runs ruff + pyright over staged + unstaged + untracked `.py` files only.

Both scripts auto-cd to repo root, so they work from any subdirectory.

**Workflow:**
1. Pick the right script (or direct invocation for a scoped target).
2. Report all findings from both tools.
3. Fix issues the user asks to fix, or summarise if they just want a report.
