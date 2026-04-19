# Tavern

A character interaction tool that generates dialogue **between** characters while you direct. Built as a prototype for RPG conversation systems.

> **This app is purpose-built to be used with [Claude Code](https://claude.ai/claude-code).** The frontend is a thin UI — all generation, repacking, and orchestration is handled by Claude Code running locally against your files. Without Claude Code, the app can display existing data but cannot generate anything new.

---

## What It Does

Instead of a single AI playing a character talking *to you*, Tavern has Claude orchestrate a conversation *between* two or more characters (up to 4). You are the director — you choose the characters, set the scene, and steer the dialogue round by round.

Two dialogue modes are available:
- **Standard mode** — full first-person prose where characters combine speech, actions, and interior thoughts
- **Narrator mode** — characters only speak; a neutral narrator handles all physical descriptions in third person

You can also switch to **player mode**, where you take control of one character and type their lines directly while the AI generates everyone else's reactions.

Characters are imported from SillyTavern-compatible PNG card files. Claude repacks them into a normalized internal format on first use, then uses that data to drive consistent, character-faithful dialogue.

---

## How It Works

The app and Claude Code communicate through a file-based task queue (`infrastructure/queue/queue.json`). There is no backend server.

```
Web App (Svelte + Vite)          Claude Code (you trigger this)
        │                                │
        ├─ writes queue.json ───────────►├─ reads queue.json (FIFO)
        ├─ pauses UI                     ├─ routes tasks by type
        ├─ polls queue.json              ├─ spawns subagents (Sonnet/Haiku)
        │                                ├─ writes results to disk
        └─ resumes when queue empty ◄────└─ clears completed tasks
```

1. The UI writes pending tasks to the queue and pauses.
2. You tell Claude Code to **run the queue**.
3. Claude Code processes tasks in order, writing results to disk.
4. The UI detects the empty queue and resumes with the new data.

---

## Prerequisites

- [Node.js](https://nodejs.org/) (v18+)
- [Claude Code](https://claude.ai/claude-code) installed and authenticated

---

## Setup

```bash
npm install
npm run dev
```

Open the local URL shown in the terminal (typically `http://localhost:5173`).

Copy `.env.example` to `.env.local` and adjust values as needed (see [Configuration](#configuration) below).

---

## Usage

### 1. Import characters

Drop SillyTavern-compatible PNG character cards into `infrastructure/raw/`. They will appear in the **Raw** list in the Characters panel.

Repacked characters (already processed) appear in the **Repacked** list and are ready to use immediately.

### 2. Select 2-4 characters and start a scene

Pick characters from either list. Raw characters are repacked automatically during scene setup. Click **Begin** to queue the scene setup tasks.

### 3. Run the queue — in Claude Code

When the UI pauses and shows it is waiting, switch to Claude Code and say:

> **"run queue"**

Claude Code will process all pending tasks — repacking any raw characters, then generating an optimized scenario tailored to the specific character combination. When it finishes, the UI resumes automatically.

### 4. Choose a leading character and opening line

The UI presents the generated scenario and a set of opening line options for each character. Select which character leads (appears on the right) and which opening line to start with. Click **Start Dialogue**.

The UI queues the first reply task and pauses again.

### 5. Run the queue again

Back in Claude Code:

> **"run queue"**

Once processed, the dialogue panel opens with the first exchange already written.

### 6. Continue the dialogue

From the dialogue panel you can:

| Action | How |
|--------|-----|
| **Continue** | Click Continue — the planner decides who speaks this round and in what order |
| **Continue with direction** | Enter a steering note before clicking Continue |
| **Roll back** | Remove the last round without involving Claude |

Each Continue queues a task. Run the queue in Claude Code to generate the next round. Turns appear in the UI progressively as they are generated — you can watch each character's response arrive in real time.

---

## Dialogue Modes

Set `TAVERN_CHAT_MODE` in your `.env.local` to switch modes.

### Standard Mode (`normal`)

The default. Each round has a fixed structure — every speaking character gets one turn combining speech, actions, and interior thoughts in first-person prose.

- Scenario-driven: each character has a tailored scenario generated at scene setup
- Formatting: `"speech"`, `*actions*`, `` `interior thoughts` ``
- Round protagonist system: one character drives the beat, others react

### Narrator Mode (`narrator`)

Characters produce **only** quoted dialogue. A neutral narrator describes all physical actions, environment, and body language in third person.

- Variable-length rounds: NPCs converse freely; the round ends when player input is needed
- Goal-driven: scenes are anchored by explicit goals instead of scenarios
- Two narrator registers (set via `TAVERN_NARRATOR_VOICE`):
  - `neutral` — clean, transparent, present tense
  - `literary` — slightly more descriptive and atmospheric
- Intelligent routing: fully-scripted dialogue is written directly (zero tokens); narrator beats and reactive speech are expanded by lightweight agents

Switching modes between rounds is supported (narrator to standard is implemented; the reverse is planned).

---

## Player Mode

Set `TAVERN_VERBATIM=on` to play as a character instead of directing from the outside.

- One character is designated as yours — you type their dialogue directly in the chat input
- The AI generates reactions from all other characters
- Works in both standard and narrator modes
- `characters.json` must have a `player_id` field pointing to your character

When player mode is off (the default), you are the director: all characters are AI-generated, and you steer with scene direction prompts.

---

## File Structure

```
tavern/
├── domain/                    # Domain knowledge and data contracts
│   ├── character/schema.md
│   └── dialogue/
│       ├── writing_rules.md
│       └── scene_structure.md
├── application/               # Agent instructions (Claude Code reads these)
│   ├── character/repack.md
│   ├── dialogue/
│   │   ├── generate_reply_plan.md          # Standard-mode planner
│   │   ├── generate_reply_plan_narrator.md # Narrator-mode planner
│   │   ├── generate_reply_turn.md          # Standard-mode turn expansion
│   │   ├── expand_character_narrator.md    # Narrator-mode character speech
│   │   ├── expand_round_narrator.md        # Narrator-mode narration
│   │   ├── validate_plan.md                # Plan structural validation
│   │   ├── optimize_scenario.md
│   │   └── condense_memory.md
│   └── scripts/               # Python CLI scripts
│       ├── card_extract.py         # Extract JSON + avatar from PNGs
│       ├── build_context_cache.py  # Pre-build character context for agents
│       ├── build_active_lorebook.py # Per-round lorebook filtering
│       ├── extract_last_turn.py    # Extract prior turn for reaction context
│       ├── merge_reply.py          # Merge turn files into final output
│       ├── append_turns.py         # Append completed round to chat history
│       ├── preview_turn.py         # Rebuild UI preview as turns land
│       ├── split_plan_by_speaker.py # Slice plan for narrator-mode isolation
│       └── enqueue.py              # Portable queue append
├── infrastructure/            # All runtime data (not committed to git)
│   ├── characters/            # Repacked character profiles
│   ├── dialogues/             # Dialogue sessions
│   ├── queue/queue.json       # Task queue
│   └── raw/                   # Source character card PNGs
└── src/                       # Svelte frontend source
```

---

## Customization

Agent instruction files ship as neutral baselines. To extend them — for example to add content rules or generation styles — create an adjacent `.overwrite.md` file:

```
application/character/repack.md           <- baseline (tracked)
application/character/repack.overwrite.md <- your extension (gitignored)
```

Overwrite files are read by agents before execution and merged with the baseline. They are excluded from version control so your local modifications stay local.

The same pattern applies to any file under `domain/` or `application/`.

---

## Configuration

Copy `.env.example` to `.env.local` and set the values you want. Claude Code reads this before every queue run.

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `TAVERN_MODE` | `run` / `dev` | `run` | `run` restricts writes to `infrastructure/` only |
| `TAVERN_CHAT_MODE` | `normal` / `narrator` | `normal` | Dialogue structure (see [Dialogue Modes](#dialogue-modes)) |
| `TAVERN_PLANNER` | `sonnet` / `haiku` | `haiku` | Model used for the planning phase |
| `TAVERN_VERBATIM` | `off` / `on` | `off` | Director mode vs player mode (see [Player Mode](#player-mode)) |
| `TAVERN_NARRATOR_VOICE` | `neutral` / `literary` | `neutral` | Narrator register (narrator mode only) |

---

## Tech Stack

### Frontend
| | |
|---|---|
| [Svelte 5](https://svelte.dev/) | UI framework — uses runes (`$state`, `$derived`, `$props`) |
| [Vite 8](https://vite.dev/) | Dev server and bundler; also serves the local file API via middleware |
| [Tailwind CSS v4](https://tailwindcss.com/) | Utility-first styling |
| [DaisyUI v5](https://daisyui.com/) | Component library on top of Tailwind |
| [marked](https://marked.js.org/) | Markdown rendering for dialogue output |

### AI / Orchestration
| | |
|---|---|
| [Claude Code](https://claude.ai/claude-code) | Primary runtime — processes the queue, calls agents, writes results |
| [claude-sonnet-4-6](https://anthropic.com/) | Character repacking, scenario generation, dialogue planning and expansion |
| [claude-haiku-4-5](https://anthropic.com/) | Plan validation, lorebook filtering, narrator-mode turn agents |

### Storage
| | |
|---|---|
| Local filesystem | All character data, dialogue history, and queue state as JSON |
| localStorage | Active scene persistence across page reloads |

### Dev Tools
| | |
|---|---|
| [ESLint](https://eslint.org/) | Linting — `eslint-plugin-svelte` for Svelte 5 rune support |
| Python 3 | CLI scripts for card extraction and context building |

---

## Model Assignment

| Task | Model |
|------|-------|
| Character repacking | `claude-sonnet-4-6` |
| Scenario generation | `claude-sonnet-4-6` |
| Dialogue planning | `claude-sonnet-4-6` or `claude-haiku-4-5` (configurable via `TAVERN_PLANNER`) |
| Plan validation | `claude-haiku-4-5-20251001` |
| Turn expansion (standard) | `claude-sonnet-4-6` |
| Turn expansion (narrator) | `claude-haiku-4-5-20251001` |
| Narrator prose | `claude-haiku-4-5-20251001` |
