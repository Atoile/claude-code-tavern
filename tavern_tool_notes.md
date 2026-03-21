# Tavern Tool — Project Notes
*Compiled from design conversations*

---

## Overview

A personal character interaction tool built as a side project prior to the main RPG. Workflow lessons learned here are directly applicable to the in-game conversation system.

**Type:** Web application
**UI Style:** Mobile chat-inspired
**Purpose:** Generate dialogue *between* characters rather than user-facing roleplay
**Timeline:** ~1-2 evenings with Claude Code

---

## Core Concept

Instead of one AI instance playing a character talking to the user, Claude orchestrates dialogue **between characters** — the user acts as a director/author rather than a participant. Each scene is a generated conversation between two or more characters.

---

## Character Cards

- Imports **SillyTavern compatible character cards** (PNG with embedded JSON)
- On import, **Claude Sonnet repacks the card data** into an optimized internal structure
- Repacking uses Sonnet (not Haiku) because card formats vary wildly:
  - Properly structured JSON
  - List of attributes
  - Detailed info with MBTI
  - Interview format
  - Plain prose descriptions
- Sonnet does the interpretive synthesis once; everything downstream gets clean reliable data

### Repacked Structure Includes
- Core personality traits (normalized)
- Speech patterns and vocabulary tendencies
- Relationship defaults and behavioral tendencies
- Voice archetype assignment
- Physical description (normalized for portrait generation)
- Magic/ability summary if relevant

---

## Scene System

- **Scene setting:** Simple text field describing the scene and direction
- **Round-based generation:** Player prompts Claude Code to continue — generates a full round of dialogue
- **Steering:** Player can include directional guidance when prompting for the next round
- **Round removal:** Last round can be deleted programmatically — no Claude involvement needed
- **Memory:** Each scene starts fresh — no memory carried between separate sessions

---

## Queue Architecture

The app does not call Claude Code automatically. Instead:

1. App **pauses** and writes pending tasks to `queue.json`
2. Player manually triggers Claude Code: *"process the queue"*
3. Claude Code processes tasks **FIFO**, calling appropriate agents per task type
4. Results written to output location, completed items removed from queue
5. App watches `queue.json` — when empty, **unpauses** and reads results

### Queue Task Format
Each item in `queue.json` is self-contained:
- Character data
- Scene context
- Task type (dialogue generation, card repacking, SDXL prompt, etc.)
- Output destination
- Model assignment (Sonnet vs Haiku)

### Agent Hierarchy
- **Claude Code** — manually triggered by player, sets everything in motion
- **Haiku** — orchestrates queue, routes tasks, calls Sonnet when needed
- **Sonnet** — handles creative/interpretive tasks

Haiku can call Sonnet by simply specifying `claude-sonnet-4-20250514` as the model parameter in API calls — model selection is just a parameter, any orchestrator can call any model.

---

## Model Assignment

| Task | Model | Reason |
|------|-------|--------|
| Dialogue generation | Sonnet | Core creative output — quality matters |
| Scene direction interpretation | Sonnet | Nuanced steering understanding |
| Queue orchestration | Haiku | Cheap coordinator, minimal creative judgment |
| Character card repacking | Sonnet | Interpretive synthesis from varied formats |
| SDXL prompt generation | Haiku | Structured transformation, no creative judgment |
| Voice archetype assignment | Haiku | Classification task |

---

## Voice System

### TTS Engine
- **XTTS v2** — local, GPU accelerated (5070Ti), proper voice cloning from audio samples
- Chosen over Kokoro for flexibility — distinct cloned voices per archetype rather than preset selection

### Voice Architecture
- **One voice model per character archetype** — not per individual character
- Archetype assigned automatically by Haiku during card repacking
- UI allows override if automatic assignment misses the mark

### Archetype Dimensions
Archetypes drawn from combinations of:
- Role (warrior, scholar, clergy, merchant, noble, commoner)
- Personality axis (dominant/submissive, warm/cold, serious/playful)
- Age/experience tier

### Default Voice Library
- Start with whatever XTTS v2 ships with by default
- Add custom voices when appropriate source material is found
- Good sources: audiobooks, voice acting reels, indie game voice acting, podcast hosts
- Requirements: clean audio without music/effects, 10-30 seconds minimum

### Voice UI
- Default voice auto-assigned on card import
- Character settings panel with audition option — play each available voice on a neutral sample line
- Override saves to local storage with the character

### Audio Validation
- **Whisper (local)** — transcribes generated audio to verify text matches intended output (catches XTTS word mangling)
- **Gemini Flash** — for nuanced voice character assessment if needed
- **Manual review** — primary method for subtle issues; XTTS is fairly consistent once voice model is dialed in

---

## Image Generation

### SDXL Integration
- Generates character portraits and potentially other visuals
- Prompts generated by **Haiku** based on repacked character data
- Style consistency maintained through base prompt template + LoRAs

### Portrait Validation
- **Gemini 2.5 Flash** (free tier, 500 req/day) — assesses whether portrait matches character description
- CLIP score as optional cheap first-pass filter for obvious failures
- Manual review for detail-critical cases
- Art style consistency handled by prompt engineering and LoRAs, not validation

---

## Image Validation — Gemini Free Tier

| Model | Daily Limit | RPM | Use Case |
|-------|------------|-----|----------|
| Gemini 2.5 Pro | 100/day | 5 | Overkill for this use case |
| Gemini 2.5 Flash | 500/day | 10 | Portrait and character validation |
| Gemini 2.5 Flash-Lite | 1000/day | 15 | Bulk icon validation |

- Limits are **per model, not shared** — can exhaust Flash then continue on Flash-Lite
- Google has precedent for reducing free tier quotas without notice — don't hard-depend on specific numbers
- Combined 1500 requests/day is more than sufficient for personal asset generation

---

## Persistence

- All conversations and chat rooms **saved locally**
- Can be continued at any time
- No backend required — pure frontend with local storage
- Character voice overrides saved with character data

---

## UI Structure

- Mobile chat-inspired layout
- Character avatars pulled from card PNG (embedded in SillyTavern format)
- One character left, one character right — distinct colors per character
- Scene context displayed at top of conversation
- **Dedicated character settings panel** — not inline editing
- Settings panel includes: character info, voice selection with audition, portrait, archetype tags

---

## Applicability to Main Game

The tavern tool prototypes several systems directly applicable to the RPG:

| Tavern Tool | RPG Equivalent |
|-------------|----------------|
| Character card repacking | NPC data structure |
| Round-based dialogue generation | In-game conversation system |
| Scene context + steering | Dialogue trigger + direction |
| Queue architecture | Any background generation task |
| Voice archetype system | NPC voice assignment |
| SDXL portrait pipeline | Character avatar generation |

---
*Notes compiled from extended design conversation — March 2026*
