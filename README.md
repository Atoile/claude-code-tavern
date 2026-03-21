# Tavern

A character interaction tool that generates dialogue **between** characters while you direct. Built as a prototype for RPG conversation systems.

> **This app is purpose-built to be used with [Claude Code](https://claude.ai/claude-code).** The frontend is a thin UI — all generation, repacking, and orchestration is handled by Claude Code running locally against your files. Without Claude Code, the app can display existing data but cannot generate anything new.

---

## What It Does

Instead of a single AI playing a character talking *to you*, Tavern has Claude orchestrate a conversation *between* two characters. You are the director — you choose the characters, set the scene, and steer the dialogue round by round.

Characters are imported from SillyTavern-compatible PNG card files. Claude repacks them into a normalized internal format on first use, then uses that data to drive consistent, character-faithful dialogue.

---

## How It Works

The app and Claude Code communicate through a file-based task queue (`infrastructure/queue/queue.json`). There is no backend server.

```
Web App (Svelte + Vite)          Claude Code (you trigger this)
        │                                │
        ├─ writes queue.json ───────────►├─ reads queue.json (FIFO)
        ├─ pauses UI                     ├─ routes tasks by type
        ├─ polls queue.json              ├─ calls Claude API (Sonnet/Haiku)
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
- An Anthropic API key accessible to Claude Code

---

## Setup

```bash
npm install
npm run dev
```

Open the local URL shown in the terminal (typically `http://localhost:5173`).

---

## Usage

### 1. Import characters

Drop SillyTavern-compatible PNG character cards into `infrastructure/raw/`. They will appear in the **Raw** list in the Characters panel.

Repacked characters (already processed) appear in the **Repacked** list and are ready to use immediately.

### 2. Select two characters and start a scene

Pick any two characters from either list. Raw characters are repacked automatically during scene setup. Click **Begin** to queue the scene setup tasks.

### 3. Run the queue — in Claude Code

When the UI pauses and shows it is waiting, switch to Claude Code and say:

> **"run queue"**

Claude Code will process all pending tasks — repacking any raw characters, then generating an optimized scenario tailored to the specific pair. When it finishes, the UI resumes automatically.

### 4. Choose a leading character and opening line

The UI presents the generated scenario and a set of opening line options for each character. Select which character leads (appears on the right) and which opening line to start with. Click **Start Dialogue**.

The UI queues one more task (the other character's first reply) and pauses again.

### 5. Run the queue again

Back in Claude Code:

> **"run queue"**

Once processed, the dialogue panel opens with the first exchange already written.

### 6. Continue the dialogue

From the dialogue panel you can:

| Action | How |
|--------|-----|
| **Continue** | Click Continue — queues a reply from both characters |
| **Continue with direction** | Enter a steering note before clicking Continue |
| **Roll back** | Remove the last round without involving Claude |

Each Continue queues a task. Run the queue in Claude Code to generate the next round.

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
│   │   ├── optimize_scenario.md
│   │   └── generate_reply.md
│   └── scripts/               # Python CLI scripts (TTS, image gen — optional)
├── infrastructure/            # All runtime data (not committed to git by default)
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
application/character/repack.md           ← baseline (tracked)
application/character/repack.overwrite.md ← your extension (gitignored)
```

Overwrite files are read by agents before execution and merged with the baseline. They are excluded from version control so your local modifications stay local.

The same pattern applies to any file under `domain/` or `application/`.

---

## Model Assignment

| Task | Model |
|------|-------|
| Character repacking | `claude-sonnet-4-6` |
| Scenario generation | `claude-sonnet-4-6` |
| Dialogue generation | `claude-sonnet-4-6` |
| Queue orchestration | `claude-haiku-4-5-20251001` |
