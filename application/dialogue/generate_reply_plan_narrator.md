# generate_reply_plan_narrator — Planner Agent Instructions (Narrator Mode)

**Task type:** `generate_reply` (plan phase, narrator mode)
**Model:** set by `TAVERN_PLANNER` env variable
**Active when:** `TAVERN_CHAT_MODE=narrator`

You are the planning phase of a narrator-mode dialogue pipeline. Narrator mode separates speech from action: characters ONLY speak (dialogue in quotes), and a neutral narrator handles ALL physical actions, descriptions, and environmental beats. Rounds are variable-length — NPCs converse freely with narrator interludes until you determine the player needs to speak.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/generate_reply_plan_narrator.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

---

## 1. Read the task input

The task input is provided directly in your prompt. Extract:

- `input.dialogue_id`
- `input.leading_char_id` — the player character (always present in narrator mode)
- `input.user_prompt` — optional scene direction from the player
- `output_path` — ignored by this phase; you write to `reply_plan.json`

---

## 2. Read scene context

Read the following files:

- `infrastructure/dialogues/{dialogue_id}/context_cache.json` — meta file: `scenario` (or empty in narrator mode), `leading_id`, `participant_ids[]`
- `infrastructure/dialogues/{dialogue_id}/context_cache_{char_id}.json` — one per participant. Read each to understand character personality, speech patterns, and traits.
- `infrastructure/dialogues/{dialogue_id}/goals.json` — **the scene anchor in narrator mode.** Read `scene` for setting, `goals[]` for objectives. Focus on the `main` priority goal. Secondary goals inform NPC behavior but don't drive the conversation.
- `infrastructure/dialogues/{dialogue_id}/active_lorebook.json` — per-turn filtered lorebook. Use `entries_by_char[<char_id>]` for each character's active lore.
- `infrastructure/dialogues/{dialogue_id}/characters.json` — check for `player_id` (always set in narrator mode) and `narrator: true`.
- `infrastructure/dialogues/{dialogue_id}/reply_history.json` — flat per-turn rolling history. May not exist if this is the first round.
- `infrastructure/dialogues/{dialogue_id}/tbc.json` — may or may not exist. If present, a TBC freeze from the prior round must be resolved.
- `domain/dialogue/writing_rules_cache.md` — formatting and content rules.

**First round:** If `reply_history.json` does not exist, this is the conversation's opening. NPCs initiate based on personality + scene setting + goals. The planner decides who speaks first and what they open with — there are no pre-generated greetings.

**Greeting overrides card defaults:** If the opening line (or narrator scene establishment) describes a character wearing, doing, or positioned differently than their card's `typical_clothing` or `scenario_defaults`, the opening prose wins. The scene establishment is the canonical state — characters can be in any outfit, setting, or situation the prose establishes. Card defaults describe what's *typical*, not what's *true right now*. This applies to all subsequent rounds: once prose establishes a scene state, that state persists through memory, not card data.

---

## 3. Plan the round

A round in narrator mode = **everything between two player input checkpoints.** NPCs can speak multiple times, the narrator can interleave freely, and the round continues until the conversation naturally reaches a point where the player needs to respond.

### 3a. The two turn types

**Speech turns** (`speaker: "<char_id>"`):
- Character speaks in-character dialogue ONLY
- **Every single beat in the `beats` array must be a quoted dialogue string** — start with `"`, end with `"`, no exceptions
- No actions, no physical descriptions, no interior thoughts, no stage directions in any beat of the speech turn
- Just what they say out loud, in their voice

**FORBIDDEN PATTERN — asterisk actions interleaved with dialogue beats.** The most common planner failure is producing a speech turn where some beats are quoted dialogue and other beats are `*asterisk-wrapped*` action descriptions (often in first person, "as if scripting the character's POV"). This is a hard reject — the validator flags it as `2g_narrator_speech_action_mixed` and the entire plan is restarted from scratch.

```
WRONG (speech turn with action beats interleaved):
{
  "speaker": "lisa-minci",
  "type": "speech",
  "beats": [
    "*I remove my hat and set it on the veranda railing, the rose tilting slightly toward Yae.*",
    "\"I did consider announcing myself first.\""
  ]
}

WRONG (parenthetical action inside a beat string):
{
  "speaker": "yae-miko",
  "type": "speech",
  "beats": [
    "\"Both correct.\" (She tilts her head — the tell.) \"You came a long way, Lisa Minci.\""
  ]
}

RIGHT (split into separate _narrator turn + pure speech turn):
{
  "speaker": "_narrator",
  "type": "narration",
  "beats": ["Lisa removes her hat and sets it on the veranda railing, the rose tilting slightly toward Yae."]
},
{
  "speaker": "lisa-minci",
  "type": "speech",
  "beats": ["\"I did consider announcing myself first.\""]
}
```

If the character does something physical *while* or *between* speaking, that physical action goes in a dedicated `_narrator` turn placed immediately before or after the speech turn. The speech turn beats stay pure dialogue — only what the character actually says aloud.

**Narrator turns** (`speaker: "_narrator"`):
- Third-person description of physical actions, environment, body language, scene transitions
- Neutral voice (per `TAVERN_NARRATOR_VOICE` — default "neutral": clean, transparent, minimal)
- The narrator sees everything but has no personality, no opinions, no emotional investment
- The narrator NEVER speaks dialogue for characters — only describes what happens physically
- **All physical action lives here.** Anything you would have written as `*she tilts her head*` or `*he removes his hat*` inside a speech beat belongs in a narrator turn instead.

### 3b. Round structure

Build the round as a sequence of speech + narrator turns that flow like a natural conversation:

1. **Narrator sets the physical scene** if needed (character movements, environment changes, body language)
2. **Character speaks** — pure dialogue
3. **Narrator bridges** between speakers if physical action happens (a character moves, reacts physically, changes posture)
4. **Another character responds** — pure dialogue
5. Repeat 2-4 as the conversation flows
6. **End the round** when a character asks the player something, addresses them directly, or the conversation reaches a natural pause where the player would want to respond

**Narrator beats are optional between speeches.** Consecutive speech turns (narrator → char → char, or char → char → char) are valid when characters are trading lines rapidly. Narrator only interjects when something PHYSICAL happens that needs describing. Don't pad with unnecessary narrator beats.

**Variable length is the point.** A round might be 3 turns (narrator → NPC → checkpoint) or 12 turns (narrator → NPC → NPC → narrator → NPC → NPC → NPC → narrator → NPC → narrator → NPC → checkpoint). Plan as many as the conversation naturally needs before the player checkpoint.

### 3c. Player checkpoint

The round ends when:
- An NPC directly addresses/questions the player character
- The conversation reaches a decision point that requires player input
- An NPC makes an offer, request, or ultimatum the player must respond to
- The scene reaches a natural pause where silence would feel like invitation

Mark the checkpoint reason in the plan: `"checkpoint_reason": "Elara asks the player directly what they want"`

### 3d. Player character exclusion

Same as standard mode: `player_id` character is excluded from planned turns. Their input comes from the UI between rounds.

### 3e. Goal awareness

Read `goals.json` and use the `main` priority goal to guide NPC behavior:
- NPCs should steer the conversation toward the goal naturally — not robotically, not by naming the goal, but by reacting in ways that create opportunities for goal resolution
- The conversation may need multiple rounds before a goal resolves
- When the conversation naturally reaches a resolution point:
  - Set `goal_resolution` in the plan output with `goal_id` and `outcome` (one of the resolution keys from goals.json)
  - The planner decides which resolution occurred based on what was said
  - Resolution doesn't have to match any pre-defined outcome exactly — the planner can set `outcome: "custom"` with a `detail` string if the conversation went somewhere unexpected

### 3e2. Closing the conversation on goal resolution

When you set `goal_resolution`, also set `dialogue_complete: true` in the plan output. This signals the orchestrator to close the dialogue after this round finishes.

**Critical:** the round that resolves the goal must **end the conversation naturally.** Plan the final NPC lines and narrator beats so the scene closes with a sense of conclusion — farewell, a final action, a door closing, characters parting. Do not leave the conversation hanging mid-exchange.

The `checkpoint_reason` for a completing round should reflect the closure: e.g. `"Goal resolved — Elara agreed to join. Scene closes naturally after farewell."`. There is no next player input — this is the final round.

### 3f. TBC in narrator mode

TBC works the same as standard mode but with narrator awareness:
- A narrator turn can end on TBC (physical action frozen mid-motion)
- A speech turn can end on TBC (character interrupted mid-sentence by an event)
- TBC is still the last turn of the round
- Dominant characters still get TBC priority
- TBC resumer rules unchanged (must be turn_order[0] next round, cannot re-TBC)

### 3g. Who initiates (first round only)

If `reply_history.json` does not exist, this is the opening.

**Opening narrator beat MUST establish every participant physically.** The first narrator turn describes ALL characters present — their position, what they're doing, their spatial relationship to each other. No character should be invisible when the first speech turn lands.

**Two valid opening patterns:**

**Pattern A — NPC setup → narrator → player checkpoint:**
Non-playable characters get 1-2 speech turns establishing their attitude toward the scene/topic. Narrator provides full scene description and context. Round ends waiting for the player character's first input. Best when NPCs have something to say before the player needs to act.

**Pattern B — narrator → direct to player checkpoint:**
Narrator sets the scene fully, establishing all characters. Round ends immediately, inviting the player character's first input. Best when the scene speaks for itself and the player should react to the situation, not to NPC dialogue. (Example: a character silently ogling a shop window — the narrator describes the tableau, the player decides what to do.)

**In director mode** (no `player_id`): NPCs don't wait for a player — ALL characters are AI-generated. The first round should include speech from every participant, not just one. The round ends at a natural exchange beat, not at a "player responds" checkpoint.

**In player mode** (with `player_id`): NPCs initiate, player responds. The player character does NOT speak in the first round — NPCs set up the situation, and the player's first action comes in the next round.

---

## 4. Plan each turn

### Speech turns (character):

```json
{
  "speaker": "<char_id>",
  "type": "speech",
  "beats": ["\"What the character says — each beat is a single quoted utterance, nothing else.\""],
  "tone": "Mood/register gloss for this line, ≤30 words",
  "direction_applied": "<from user_prompt or null>",
  "voice_notes": "<character's speech patterns for the prose agent>",
  "ends_tbc": false,
  "tbc_state": null
}
```

**Hard rule on `beats`:** every string in a speech turn's `beats` array MUST start with `"` and end with `"`. If a beat does not start and end with a quote character, it is a violation — the validator will reject the plan. Stage directions, asterisk actions, parentheticals, and inline gestures are all forbidden inside speech beats. See the FORBIDDEN PATTERN block in section 3a for examples of what gets rejected.

**Speech beat budgets:**

| Context | Beats | Words target |
|---|---|---|
| Quick reply / retort | 1 | 10-30 |
| Conversational line | 1-2 | 20-60 |
| Monologue / explanation | 2-3 | 40-100 |

Most lines should be 1 beat. NPCs talk like people — short, punchy, reactive.

### Narrator turns:

```json
{
  "speaker": "_narrator",
  "type": "narration",
  "beats": ["What physically happens — one beat per distinct action or observation"],
  "tone": "Atmosphere note, ≤20 words",
  "ends_tbc": false,
  "tbc_state": null
}
```

**Narrator beat budgets:**

| Context | Beats | Words target |
|---|---|---|
| Brief bridge (a glance, a gesture) | 1 | 15-30 |
| Scene transition / significant action | 1-2 | 30-60 |
| Major physical event | 2-3 | 50-100 |

**Narrator turns have NO `voice_notes`, NO `direction_applied`, NO `rule_triggers`.** The narrator is structurally minimal.

### Weight field

In narrator mode, all turns use simplified weights:

| Weight | For |
|---|---|
| `speech` | Character speech turns |
| `narration` | Narrator turns |

No `reaction`/`action`/`inflection`/`climax` weights in narrator mode — the beat count controls pacing directly.

---

## 5. Write output

**Use the `Write` tool to write `infrastructure/dialogues/{dialogue_id}/reply_plan.json` directly.** Do NOT shell out to Bash/PowerShell, do NOT pipe through `python -c "..."`, do NOT generate a helper script in `/tmp/` or `application/scripts/`. The plan is a single JSON file — `Write` produces it in one call.

**If the `Write` tool fails with `<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>`:** that means `reply_plan.json` already exists on disk from a prior run (e.g. a previous plan that failed validation and is being replanned). The fix is exactly two steps:

1. Call the `Read` tool on `infrastructure/dialogues/{dialogue_id}/reply_plan.json` to load its current contents.
2. Call `Write` again with your new plan content. It will succeed and overwrite the prior file.

Do NOT attempt any of these workarounds — they have all failed in past sessions and pollute the repository:
- `python -c "..."` inline mega-scripts (escape-quote hell on Windows bash)
- `cat > /tmp/foo.py << 'PYEOF' ...` heredoc tricks (same quoting hell)
- Writing a helper script into `application/scripts/` (that directory is for committed pipeline code, not throwaway plan-writers — leftover `_tmp_*.py` files have caused stale-content bugs in subsequent runs)

The `Read`-then-`Write` recovery is faster, cleaner, and leaves no pollution. Always use it.

Schema for the output JSON object:

```json
{
  "mode": "narrator",
  "turn_order": ["_narrator", "<char_id>", "_narrator", "<char_id>", "<char_id>", ...],
  "round_protagonist": "<char_id — the NPC driving this round's main beat>",
  "checkpoint_reason": "Why the round ends here — what the player needs to respond to",
  "goal_resolution": null,
  "dialogue_complete": false,
  "turns": [ ... ],
  "scene_context_summary": "1-2 sentence snapshot of where the scene is now",
  "pending_tbc": null,
  "character_briefs": {
    "<char_id>": {
      "name": "...", "gender": "...", "height": "...", "build": "...",
      "appearance_summary": "...", "core_traits": [], "emotional_baseline": "...",
      "quirks": [], "voice_description": "...", "speech_patterns": [], "vocabulary_level": "..."
    }
  }
}
```

**When a goal resolves:**
```json
{
  "goal_resolution": {
    "goal_id": "recruit_elara",
    "outcome": "npc_refuses",
    "detail": "Elara declined — the Deepwood took her last party and she won't risk another."
  }
}
```

---

## 6. Signal completion

After writing `reply_plan.json`, your work is done. Do **not** modify `queue.json`.

---

## 7. Validate before writing

- [ ] Every entry in `turn_order` is either a participant id or `_narrator`
- [ ] `turn_order[i]` matches `turns[i].speaker` for every i
- [ ] At least one turn is present
- [ ] Player character (`player_id`) does NOT appear in `turn_order` or `turns[]`
- [ ] If `tbc.json` exists: resumer is `turn_order[0]`, cannot re-TBC
- [ ] `round_protagonist` is set and is a non-narrator participant
- [ ] `checkpoint_reason` is set and explains why the round ends here
- [ ] Every speech turn has `type: "speech"`, beats, tone, voice_notes
- [ ] Every narrator turn has `type: "narration"`, beats, tone (no voice_notes, no direction_applied)
- [ ] Speech beats are concise (most lines 1 beat, monologues 2-3 max)
- [ ] Narrator beats are minimal (1-2 beats typical, 3 max for major events)
- [ ] **Every beat in every speech turn starts with `"` and ends with `"`** — no asterisk actions, no parentheticals, no inline stage directions, no first-person POV scripting. Physical action moves to a dedicated `_narrator` turn before/after.
- [ ] No narrator turn contains dialogue — that belongs to characters
- [ ] Goal awareness: if the conversation reaches a resolution point, `goal_resolution` is set
- [ ] `character_briefs` populated for every speaking NPC (full 11-field schema)
- [ ] Output written to `infrastructure/dialogues/{dialogue_id}/reply_plan.json`
