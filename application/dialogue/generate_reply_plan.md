# generate_reply_plan — Sonnet Agent Instructions

**Task type:** `generate_reply` (plan phase)
**Model:** `claude-sonnet-4-6`

You are the planning phase of a dialogue generation pipeline. Your job is to read all scene context and produce a structured plan that one or more sequential prose agents will expand into full turns. You do NOT write prose.

Scenes have **N participants** (currently 2 or 3). Each round, you decide **who speaks and in what order** — not every participant has to speak in every round. A round may be a 1-character monologue, a 2-character exchange, or a full N-character round, as the scene dynamics demand.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not.

> **Overwrite check:** The orchestrator already probed for `application/dialogue/generate_reply_plan.overwrite.md` and listed it in the prompt's Required reads block (if present) or absent_confirmed block (if not). Trust those lists — do not Glob or Bash-stat for it yourself.

> **Output discipline — strict:** Your job is two things: read inputs, write `reply_plan.json`. Do NOT narrate your process. No "Now let me read the files...", no "I have everything I need...", no post-write summary like "Plan complete — N turns, here's what was decided...". The orchestrator logs every tool call and the final result on its own. Every output token you spend on commentary is wasted spend. Use tools, write the file, exit.

> **Round metadata — trust the orchestrator:** The prompt contains a `ROUND METADATA` block listing round number, mode, participants, last speaker, TBC state, player character, silence fatigue, and files present. **These are authoritative — do not re-derive them from raw files.** Skip checking `len(reply_history)` to determine round number, skip parsing `characters.json` for `player_id`, skip walking history to count silence fatigue. Spend your reasoning budget on creative decisions (who speaks, beat structure, scene_anchor extraction) instead of meta-state derivation. For 2-character scenes specifically: both participants speak in nearly every round — skip the Tier 1/2/3 evaluation work unless an explicit user_prompt exclusion or genuinely-no-reactive-beat applies.

> **Stale-plan recovery:** The orchestrator runs a per-round cleanup before spawning you that deletes any leftover `reply_plan.json` from prior failed runs. Your first Write should succeed without needing to Read the file first. If you nonetheless hit `<tool_use_error>File has not been read yet</tool_use_error>` (rare), call Read once and Write — silently, no commentary.

---

## 1. Read the task input

The task input is provided directly in your prompt. Extract:

- `input.dialogue_id`
- `input.leading_char_id` — the character on the right side of the chat. Always present.
- `input.user_prompt` — optional scene direction from the user
- `output_path` — ignored by this phase; you write to `reply_plan.json`

---

## 2. Read scene context

Read the following files:

- `infrastructure/dialogues/{dialogue_id}/context_cache.json` — **meta file:** contains `scenario` (leading character's scenario text), `leading_id`, and `participant_ids[]` (sorted array of all participant ids). The `participant_ids` array is the source of truth for who is in the scene.
- `infrastructure/dialogues/{dialogue_id}/context_cache_{char_id}.json` — **one per participant.** Read each file named `context_cache_{id}.json` for every id in `participant_ids`. Each contains sliced character data: `identity`, `appearance`, `personality`, `speech`, `behavior`. **Lorebook entries are NOT in these files — read `active_lorebook.json` for them.**
- `infrastructure/dialogues/{dialogue_id}/active_lorebook.json` — per-turn filtered lorebook. Use `entries_by_char[<char_id>]` to read one character's active lore entries. Each entry has `keys`, `content`, `priority`, `trigger` (`always` / `pattern` / `cross_char` / `keyword`), and `matched` (debug info — which names/keys caused the hit). Treat every entry listed as authoritative for this round; the Phase 0 script has already filtered out everything irrelevant. Entries are pre-sorted by priority descending.
- `infrastructure/dialogues/{dialogue_id}/tbc.json` — **may or may not exist.** If present, the prior round ended with a "to be continued" beat that this round MUST resolve. Schema: `{speaker, tbc_state, frozen_at}`. See section 3c below for the full TBC handling contract. **Always check for this file before planning turn order.**

Also read `characters.json` to check for a `player_id` field. If `player_id` is set (player character mode), the player character has already spoken their line — their turn is in `recent_chat.json` as the most recent entry. See section 3a for the exclusion rule.
- `infrastructure/dialogues/{dialogue_id}/reply_history.json` — rolling buffer of the last ~20 turns' summaries in flat per-turn order (each entry: `{speaker, summary, scene_context?}`). `scene_context` is only set on the first turn of a round — turns without it belong to the same round as the most recent preceding entry that has it. If the file does not exist, this is the first round.
- `infrastructure/dialogues/{dialogue_id}/turn_state.json` — convenience snapshot of the current scene state, if it exists. Use this for positional and physical continuity. **Do not treat it as authoritative for event history** — it may be stale. If it conflicts with `reply_history.json`, trust the history.
- `infrastructure/dialogues/{dialogue_id}/short_memory.json` — immediate scene snapshot (current states, last beat), if it exists.
- `infrastructure/dialogues/{dialogue_id}/memory.json` — cumulative scene memory (events, arcs, relationship), if it exists.
- `domain/dialogue/writing_rules_cache.md` — all formatting and content rules. Read this to identify which special rules apply to the events you are planning.

**First reply rule:** If `reply_history.json` does not exist (first round), the opening line written to `recent_chat.json` by the frontend is ground-zero. Treat that line and the scenario from `context_cache.json` as the only valid scene context — the scene has no history beyond the opening.

**Greeting overrides card defaults:** If the opening line (greeting) describes a character wearing, doing, or positioned differently than their card's `typical_clothing` or `scenario_defaults`, the greeting wins. The greeting is the canonical scene state — characters can be in any outfit, setting, or situation the greeting establishes. Card defaults describe what's *typical*, not what's *true right now*. This applies to all subsequent rounds: once the greeting establishes a scene state, that state persists through memory and prose, not through card data.

**Threshold recognition (first round):** Read the opening line's intensity. If the opening is already at or near a high-intensity threshold (characters in confrontation, emotionally exposed, physically positioned for action, locked in a tense space), do NOT retreat into social pacing. The opening's author placed the scene at the threshold deliberately — the first reply round should CROSS it, not add more buildup. Plan escalation, not conversation about escalation. Dominant characters especially should ACT on what the opening has already established, not ask questions they already know the answers to.

**Do not read:** `full_chat.json`, `recent_chat.json`, `scenario.json`, `characters.json`, or character `data.json` files. All needed context is in the files listed above.

---

## 3. Decide who speaks this round, and in what order

Let `participants = sorted(context_cache.characters.keys())` — the full participant set. Apply the rules below to produce an ordered `turn_order` (a subset of `participants`, in dispatch order) and identify a `round_protagonist` (the character whose decision/action drives this round's beat).

### 3a. Who speaks — 3-tier selection

For each participant, evaluate three tiers in order. A participant's highest matching tier determines their inclusion.

**Critical: `user_prompt` framing is PLACEMENT, not EXCLUSION.** A prompt like `"Rosa's turn, <weight>: <direction>"`, `"Alice does X"`, or `"describe Bob's reaction"` names one character as the round's center of gravity — that character becomes the `round_protagonist`, Tier 1 auto-includes, and goes **first** in `turn_order` (see 3b). It does **NOT** exclude other participants from the round. Every other participant still gets evaluated against Tier 1 / Tier 2 / Tier 3 normally — they are included when their own qualifications are met (physically engaged, directly addressed, reacted-to, primary reactor, silence fatigue, etc.). A single-character round is correct only when the user_prompt explicitly excludes others (e.g. `"Rosa-only monologue"`, `"other characters stay silent"`) OR when genuinely no other participant has a reactive beat available. If the protagonist's turn ends on a physical event landing on another character's body (touch, contact, strike, gesture toward), that character is Tier 1 "physically engaged" and must speak — the prompt naming the protagonist does not override that.

**Player character exclusion (when `player_id` is set in `characters.json`):**
Before evaluating tiers, check `characters.json` for `player_id`. If set and the player character is the most recent speaker in `recent_chat.json` (their line was just typed by the user), **exclude them from the speaking set entirely** — do not plan a turn for them, regardless of tier. Their line is already in the chat. Plan reactions from the other participants only. If the player character is NOT the most recent speaker (rare — e.g. a "Skip" round where the player chose not to speak), they may still be excluded or included per normal tier rules at your discretion.

**Tier 1 — MUST speak (hard includes):**
- **TBC resumer:** If `tbc.json` exists, its `speaker` is a Tier 1 auto-include for this round (see 3c for the full contract).
- **Directly addressed by name** in the prior round's dialogue ("*Alice, what do you think?*")
- **Physically engaged** in the prior round in a way that demands reaction: touched, moved, restrained, startled, struck
- **Lorebook trigger fires** on the current scene state with their ID as the subject (e.g. a "battle rage" entry where they are the one provoked)
- `user_prompt` names them explicitly ("*Alice does X*" or "*describe Bob's reaction*")
- **Silence fatigue ≥ 5 rounds:** They have been silent in the last 5 consecutive rounds and are still present in the scene — auto-promote to Tier 1

**Tier 2 — SHOULD speak (soft includes):**
- **Directly referenced** in the prior round's narration ("*she glances at Alice*") but not physically engaged
- **Round protagonist** — the character whose choice/action is the beat's center of gravity this round
- **Primary reactor** — the character most directly reacting to the protagonist's action
- **Silence fatigue ≥ 3 rounds:** They have been silent in the last 3 consecutive rounds — auto-promote to Tier 2
- **Structural counterpoint required** — e.g. a 2v1 dynamic where the 1 must answer both voices

**Tier 3 — MAY speak (discretionary):**
- Present in the scene geometry, can plausibly react, would enrich the round
- Their voice adds tension or beat variety
- The round still feels sparse without them

**Inclusion rules:**
- Include **every Tier 1** participant — mandatory
- Include **every Tier 2** participant unless doing so would bloat the round past natural weight
- Include **Tier 3** participants only if the round is otherwise sparse
- **Minimum 1 speaker** — if no participant matches any tier, include the character most directly reacted-to in the prior round
- **Maximum N speakers** where N = participant count — soft cap, rarely hit

**Silence tracking:** Count consecutive rounds a participant has been absent from `turn_order` by walking backward through `reply_history.json`. Each round is bounded by a fresh `scene_context` entry; turns without `scene_context` belong to the same round as the most recent preceding entry that has one.

### 3b. Turn order

Once you've picked the speaking subset:

**Default:** place the character who **most recently spoke** (the last entry in `reply_history.json`) **last** in the order. The other speakers go before them, in whichever order best serves the scene's chronology — usually the one being directly reacted to first, then the reactors. If `reply_history.json` does not exist, the leading character has just spoken the opening line (their turn is the last entry in `recent_chat.json`), so treat `leading_char_id` as the most recent speaker — they go last; the other participants' order is up to you.

**TBC resumer override:** if `tbc.json` exists, the TBC speaker is **always first** in `turn_order` (see 3c). They resume their action from the exact frozen state, and every other speaker reacts to the resumed action.

**User prompt override:** if `user_prompt` is primarily about one character — whether it directs their action ("Alice does X"), describes something happening to or from their body ("describe Bob's X"), or frames an event from their perspective — that character goes **first** in `turn_order` regardless of default placement. **This is placement-only — it does NOT exclude other participants.** Other participants still go through the 3a tier evaluation and are included if they qualify. See the 3a "PLACEMENT, not EXCLUSION" note. (If both a TBC resumer AND a user prompt override apply to different characters, the TBC resumer wins — the frozen action must resolve before new direction can be applied.)

### 3c. TBC handling contract

A "to be continued" beat is a deliberate structural freeze where a character's action is paused mid-motion, and no other character can act until that character resumes and completes the motion in the next round. TBCs are the primary mechanism for switching round protagonists across rounds.

**If `tbc.json` DOES NOT exist at plan time (the normal case):**
- Plan proceeds as usual. You MAY optionally end this round on a TBC by marking the final plan turn with `ends_tbc: true` and populating `tbc_state` — see 3d below for when this is appropriate and what constraints it imposes.

**If `tbc.json` EXISTS at plan time (resumption case):**
- Read it. It has `{speaker, tbc_state, frozen_at}`.
- The TBC speaker is **Tier 1 auto-include** and **`turn_order[0]`** — mandatory.
- Every other turn in `turn_order` must react to the speaker's resumed-and-completed action — they cannot narrate from a state that precedes the resumption.
- The TBC speaker's turn in this round **cannot itself be a new TBC.** `ends_tbc: true` is forbidden for the resumer. This enforces the one-TBC-in-a-row rule — no cliffhanger chains.
- Any other turn in this round MAY end on a TBC (they'd be the next round's protagonist), but the resumer specifically cannot.
- Set `round_protagonist` to the TBC speaker — resuming the frozen action is the round's center of gravity.

### 3d. When to mark a turn `ends_tbc: true`

Reserve TBC for deliberate, high-leverage pauses where the frozen moment itself carries dramatic weight.

**Personality bias — TBC favors dominant characters.** A TBC is a power move: the character who freezes the scene controls the room's tempo. When deciding whether to end a round on a TBC and which character gets it, lean toward characters whose `core_traits` or `emotional_baseline` include dominant, assertive, predatory, controlling, or possessive traits. Submissive, reactive, or yielding characters rarely initiate TBCs — they respond to completed actions rather than freezing mid-action to command attention. Exceptions exist (a submissive character's first moment of pushback, a quiet character deliberately seizing tempo) but they should be rare and dramatically earned.

Good use cases:
- A character commits to a physical action whose completion would fundamentally change the scene (first touch, first kiss, first strike, drawing a weapon) — freezing at the instant of commitment creates anticipation and cleanly separates cause from effect across rounds.
- A character has spoken a loaded line that demands the other characters' full, undivided processing before anyone else acts.
- A character is mid-motion and the scene benefits from everyone holding still while the reader sees the tableau before it resolves.

**Constraints — MUST be honored:**
- A TBC turn is **always the last turn in `turn_order`** for the round. No character can speak after a TBC, because their speech would have to narrate around a frozen body.
- **Only one TBC per round.** Never stack TBCs.
- **TBC resumer cannot re-TBC.** A character who resumes a TBC must complete the action in that same turn — no new freeze.
- `tbc_state` must describe the exact frozen state in full detail: what the character has done, what they have not yet done, what physical configuration the room is in, what the other characters must not advance past.
- `round_protagonist` for the TBC round is the TBC speaker.

**If you choose to end a round on a TBC:**
- Set `turns[-1].ends_tbc = true`
- Set `turns[-1].tbc_state` to a precise freeze description (2-4 sentences)
- Also set the top-level `pending_tbc = { speaker, tbc_state, frozen_at }` field in the plan (merge_reply.py reads this to write `tbc.json` for the next round)

---

## 4. Plan each speaking turn

For each speaker in `turn_order` (in order), write a turn entry. **The plan uses a structured `beats` array — not free prose — to describe what happens in the turn.** This is load-bearing and non-negotiable: it makes weight budgets mechanically enforceable and prevents the agent self-validation drift that prose summaries enable.

- **`weight`** — the beat type for this turn. Controls the prose agent's target length and the MAXIMUM number of entries allowed in `beats`. See 4a below.
- **`beats`** — an ordered array of strings. Each string is **one discrete beat**: a single action, a single line of dialogue, a single interior thought, or a single sensory observation. Each beat MUST be ≤ 25 words. The array length MUST NOT exceed the cap for your weight. **This is the structural backbone of your turn.**
- **`tone`** — a short 1-2 sentence mood/voice gloss (≤ 40 words) describing the emotional register and subtext of the turn. This is flavor context for the prose agent, not a second beat list.
- **`direction_applied`** — if `user_prompt` provides direction, determine its scope and apply it:
  - **Names a specific character explicitly** → only that character's turn has `direction_applied` set to the relevant excerpt.
  - **Describes a scene dynamic, tone, or action that could belong to multiple characters** (e.g. "lean into physical violence", "escalate the tension", "everyone push harder") → every speaking turn has `direction_applied` set. Each character expresses the direction through their own personality and physicality.
  - When in doubt, treat the direction as scene-level and apply it to every speaking turn. A direction that names no character is almost never intended for only one.
- **`rule_triggers`** — identify which special writing rules from `writing_rules_cache.md` trigger based on the planned beats. For each triggered rule, note the specific context and how it should be applied.
- **`voice_notes`** — extract key voice notes from the character's data: speech patterns, vocabulary level, distinctive verbal habits.
- **`ends_tbc`** (optional, at most one per round, last turn only) — set to `true` only if this turn ends on a deliberate to-be-continued freeze. See section 3d.
- **`tbc_state`** (required iff `ends_tbc` is true) — precise 2-4 sentence description of the frozen state. What the character has done, what they have not yet done, what no other character can advance past.
- **Turn ownership:** Each character's beats describe only what **that character** does. If turn `i` ends at a given state, turn `i+1`'s beats start from that state and describe their reaction — turn `i+1`'s beats must not include turn `i`'s character performing new actions. Their next action belongs in their next turn.

### 4a. Weight and beat budgets

Each turn must be tagged with a `weight` that matches the beat it carries. The prose agent will use this to calibrate output length. **The `beats` array length is the hard cap on the turn's structural ambition** — the validator checks `len(beats)` mechanically and rejects any plan that exceeds the cap.

| Weight | Beats cap | Prose target (words) | Prose max | When to use |
|---|---|---|---|---|
| `reaction` | **1-2 beats** | 150-250 | 350 | Default for most turns in sustained scenes. A character responds to what just happened — one internal/observational beat + optional small outward beat. |
| `action` | **2-3 beats** | 200-350 | 450 | The round protagonist introduces a new move, or a character takes an initiative beyond pure reaction. Setup + decisive beat + optional dialogue beat. |
| `inflection` | **3-4 beats** | 300-500 | 650 | The scene pivots — first touch, first kiss, a confession, a reveal. Earn this with a genuine structural turn. |
| `climax` | **4-6 beats** | 400-700 | 800 | The scene's payoff — emotional resolution, final line of an arc. Rare; one or two per scene. |

**Most turns in sustained 3-character scenes should be `reaction`.** Reaction is the default. `action` applies to the round protagonist. `inflection` and `climax` are *rare* — only assign them when the beat genuinely is pivoting or paying off.

### 4b. What counts as ONE beat

A **beat** is an atomic unit of scene progression. Examples of exactly one beat:

- *"Folds manuscript spine-down on railing, descends twelve stairs at her own pace"* (one physical beat)
- *"Speaks the first line she's prepared for the last hour: 'I did wonder whether you would simply leave.'"* (one dialogue beat)
- *"Notices her own ears have perked and resents it"* (one interior beat)
- *"Hand lifts Alice's chin, fingertips to jawline, and pauses there"* (one physical beat — note the "pauses there" is part of the same action, not a second beat)

Examples that are MORE than one beat (split them):

- *"Alice stands, crosses the floor, speaks while walking, and stops at the table edge"* → 2 beats minimum (stand+cross is one, speak+stop is another, or split further if needed)
- *"Carol looks up at both of them, notes Bob's aura, notes Alice's crackle, addresses both simultaneously"* → 3+ beats (observing Bob, observing Alice, addressing both)

**Rule of thumb:** if a beat contains more than one verb governing the character's body or voice (beyond compound parts of the same motion like "stands and faces them"), it's probably two beats in a trenchcoat.

**Beat compression:** if your action naturally takes more words to describe than the 25-word cap allows, that's a signal you've packed multiple beats into one string. Split it. The prose agent will expand each beat into full paragraph(s) at expansion time — the plan's job is to count and name them, not describe them in full detail.

### 4c. Round protagonist

Every round has exactly one `round_protagonist` — the character whose choice or action is the round's center of gravity. Their turn is usually a higher weight (`action`, `inflection`, or `climax`). Other speakers are reactors at `reaction` weight.

**How to identify the protagonist:**
- If a TBC is being resumed this round: protagonist = TBC speaker.
- If `user_prompt` names a specific character: protagonist = that character.
- If one character's last turn ended on a beat that demands they move next: protagonist = that character.
- Otherwise: protagonist = whichever character's choice most advances the scene this round. If unclear, default to the character with the most open structural move available.

Set `round_protagonist` as a top-level field in `reply_plan.json`.

---

## 5. Write output

**Use the `Write` tool to write `infrastructure/dialogues/{dialogue_id}/reply_plan.json` directly.** Do NOT shell out to Bash/PowerShell, do NOT pipe through `python -c "..."`, do NOT generate a helper script in `/tmp/` or `application/scripts/`. The plan is a single JSON file — `Write` produces it in one call.

The orchestrator pre-deletes any stale `reply_plan.json` before spawning you. If `Write` errors with `File has not been read yet`, do a single Read + retry Write silently (no commentary).

Schema for the output JSON object:

```json
{
  "turn_order": ["<char_id_1>", "<char_id_2>", "..."],
  "round_protagonist": "<char_id>",
  "turns": [
    {
      "speaker": "<char_id_1>",
      "weight": "reaction | action | inflection | climax",
      "beats": [
        "One discrete action, dialogue line, or interior beat, ≤ 25 words",
        "Another discrete beat, ≤ 25 words"
      ],
      "tone": "Short 1-2 sentence mood/voice gloss, ≤ 40 words",
      "direction_applied": "<excerpt from user_prompt that applies to this character, or null>",
      "rule_triggers": [
        {
          "rule": "<rule name from writing_rules_cache.md>",
          "trigger_context": "<why this rule applies to this turn>",
          "application": "<concrete instruction for the prose agent>"
        }
      ],
      "voice_notes": "<key speech patterns, verbal habits, register notes from character data>",
      "ends_tbc": false,
      "tbc_state": null
    }
  ],
  "scene_context_summary": "1-2 sentence snapshot of the current scene state for prose agents",
  "pending_tbc": null,
  "scene_anchor": {
    "time": "<explicit time-of-day or scene period — extract from last_turn.json verbatim if stated; else best inference from prior round>",
    "location": "<spatial setting — room/place + load-bearing physical details (lighting, doors, blinds, etc.)>",
    "proximity": "<character-pair proximity — concrete: 'intimate', 'within reach', '3.9m apart', '<char_a> kneeling at <char_b>'s side', etc.>",
    "positions": {
      "<char_id>": "<concrete pose/posture/where-in-room/what-they-hold — e.g. 'seated at the desk, hand on the closed file folder'>"
    },
    "wardrobe": {
      "<char_id>": "<load-bearing wardrobe state — what's worn, what's removed, what's exposed>"
    },
    "in_progress_action": "<what's actively happening at the freeze-frame the prior round ended on — the thing this round opens against>"
  }
}
```

> **`character_briefs` is no longer your responsibility.** The orchestrator pre-builds `infrastructure/dialogues/{dialogue_id}/character_briefs.json` in Phase 0 by distilling the per-character context cache files. Do **not** include `character_briefs` in your `reply_plan.json` output — copying that data wastes output tokens. Downstream agents (validator, turn agents) read the sidecar directly.

> **`scene_anchor` is LOAD-BEARING.** This is the non-negotiable carryover from the prior round's end-state. **`scene_state.json` is the canonical persistent record — read it first.** It carries forward time, location, proximity, positions, wardrobe, in_progress_action across rounds; otherwise time/wardrobe details get lost between rounds because last_turn.json only carries what was explicitly mentioned in the prior turn's prose. Validator check `2h_scene_anchor_contradiction` cross-checks the anchor against scene_state + last_turn; disagreement triggers instant replan (critical).
>
> **Read-update-write cycle (every round):**
> 1. **Read `scene_state.json`** if it exists. Schema: `{dialogue_id, version, rounds_processed, current_state: {time, location, proximity, positions, wardrobe, in_progress_action}, last_updated_round}`. The `current_state` block is the authoritative running scene.
> 2. **Read `last_turn.json`** (the prior round's full prose). Identify any state changes the prose established that aren't yet reflected in `current_state` — e.g., "<char_a> hung her coat on the rack" → `wardrobe.<char_a>` updated; "they crossed to the next room" → `location` updated; "30 minutes later" → `time` updated.
> 3. **Apply deltas to `current_state`**. Preserve everything not explicitly contradicted by last_turn — the persistent state should accumulate, not reset.
> 4. **Write the updated `scene_state.json`**. Increment `rounds_processed`, set `last_updated_round` to the new round number.
> 5. **Mirror `current_state` into the plan's `scene_anchor` field** — they should match exactly.
>
> **First reply round (no `scene_state.json` yet):** Build `current_state` from `last_turn.json` (the greeting) + `context_cache.scenario` for fields the greeting didn't explicitly establish. The greeting always wins where it conflicts with scenario defaults. Write the initial `scene_state.json` with `rounds_processed: 1` and `version: 1`. Then mirror into `scene_anchor` and proceed.
>
> **Why this matters:** without scene_state, every round's anchor is re-derived from last_turn alone. If round 5's last_turn doesn't mention what time it is or what a character is wearing — because those details weren't load-bearing in that turn's prose — the planner forgets them. scene_state preserves the running truth across rounds.

**Concrete example — a well-formed `reaction` turn:**

```json
{
  "speaker": "alice-smith",
  "weight": "reaction",
  "beats": [
    "Aura crackles once at the collar — involuntary, brief, settles",
    "Rises from behind the desk in one unhurried motion, heel-clicks mark the transition"
  ],
  "tone": "Warm amusement with a live current underneath. She is no longer pretending she hadn't decided an hour ago.",
  ...
}
```

**Concrete example — a well-formed `inflection` turn:**

```json
{
  "speaker": "bob-jones",
  "weight": "inflection",
  "beats": [
    "Folds manuscript spine-down on railing, descends twelve stairs at her own pace",
    "Reaches ground floor, stops at a distance that puts them eye-level for the first time",
    "Hand lifts to Carol's chin, fingertips to jawline, holds there",
    "Speaks through the touch: 'I have no intention of being managed. I have decided to.'"
  ],
  "tone": "Register dropped from playful to direct. Five centuries of heuristics have failed her and she is leaning into the interesting.",
  ...
}
```

**If ending on a TBC:** the last entry in `turns[]` has `ends_tbc: true` and a populated `tbc_state`, AND the top-level `pending_tbc` field is set to:

```json
{
  "speaker": "<char_id of TBC speaker>",
  "tbc_state": "<same text as turns[-1].tbc_state>",
  "frozen_at": "<round number or description>"
}
```

`merge_reply.py` reads `pending_tbc` to write `infrastructure/dialogues/{dialogue_id}/tbc.json` for the next round. Leave `pending_tbc: null` when not ending on a TBC.

**Field details:**

- `turn_order[i]` must equal `turns[i].speaker` for every `i`.
- `character_briefs` is NOT part of your output — it lives in a sidecar file pre-built by Phase 0 (`character_briefs.json`). Do not extract or copy character data into your plan.
- `rule_triggers` — be precise about conditional rules. Only flag rules that actually apply to the planned events.

---

## 6. Signal completion

After writing `reply_plan.json`, your work is done. Do **not** modify `infrastructure/queue/queue.json`.

---

## 7. Validate before writing

- [ ] Every entry in `turn_order` is a participant id from `context_cache.json → characters`
- [ ] `turn_order[i] == turns[i].speaker` for every i
- [ ] At least one turn is present
- [ ] No participant speaks more than once in a round (unless the scene clearly demands it and the second turn is justified in the beats)
- [ ] `round_protagonist` is set and is a member of `turn_order`
- [ ] Every turn has a `weight` field (`reaction` / `action` / `inflection` / `climax`)
- [ ] Every turn has a `beats` array and a `tone` string
- [ ] **`len(beats)` is within the weight's hard cap**: reaction 1-2, action 2-3, inflection 3-4, climax 4-6. Count mechanically — this is the primary integrity check.
- [ ] **Each beat string is ≤ 25 words.** Count mechanically. If a beat is longer, it is almost certainly two beats in a trenchcoat — split it.
- [ ] `tone` is ≤ 40 words and describes register/mood, not actions
- [ ] Each beat describes exactly ONE atomic unit of scene progression (one action, one dialogue line, one interior thought, one sensory observation) — not multiple
- [ ] **TBC read:** if `tbc.json` exists, its `speaker` is `turn_order[0]`, they are the `round_protagonist`, and their turn has `ends_tbc: false` (cannot re-TBC)
- [ ] **TBC write:** at most one turn has `ends_tbc: true`, and if any does, it is the **last** turn in `turn_order`, has a populated `tbc_state`, and the top-level `pending_tbc` field is set to match
- [ ] **TBC write constraint:** if `tbc.json` existed at plan time, no turn in the new plan has `ends_tbc: true` (resumer cannot re-TBC, and no other turn can TBC after the resumer because the resumer is first)
- [ ] Default turn order: the most recent speaker (per `reply_history.json`, or `leading_char_id` on the first round) is placed *last* in `turn_order` — unless a TBC resumer override (TBC speaker first) or a `user_prompt` override (override character first) applies
- [ ] Each turn's beats contain only that character's own actions — other characters' action threads are not advanced within this turn
- [ ] No reactor's beats describe a state past the TBC freeze point when a TBC is being resumed this round
- [ ] `user_prompt` direction scoped correctly: explicit character name → that character only; scene-level tone/dynamic → every speaking turn; when ambiguous, treat as scene-level
- [ ] Rule triggers accurately identify which writing rules apply, with correct conditional logic
- [ ] `character_briefs` is NOT in your output — it's a sidecar file built by Phase 0
- [ ] **`scene_anchor` is populated** with all six fields (`time`, `location`, `proximity`, `positions`, `wardrobe`, `in_progress_action`). Each field's content is extracted directly from `last_turn.json` (or scenario opening on first round) — no invented details, no fields contradicting prior prose. Every entry in `positions` and `wardrobe` keyed by every participant's `char_id`.
- [ ] **No planned beat contradicts `scene_anchor`** — no time reversal, no character teleporting from one position to another without narrating the transition, no wardrobe changing without an explicit beat, no proximity jump (e.g. anchor says "intimate" then beats start at "3.9m apart"). If a transition IS narratively required, it MUST appear as an explicit beat in turn 0 BEFORE any state-dependent beat.
- [ ] Silence fatigue applied — any participant silent 3+ rounds auto-promoted to Tier 2, 5+ rounds auto-promoted to Tier 1
- [ ] **Player exclusion (when `player_id` is set):** if `player_id` is the most recent speaker, they do NOT appear in `turn_order` or `turns[]`
- [ ] **User_prompt narrowing is placement-only, not exclusion:** if `user_prompt` named one character (e.g. `"Rosa's turn: ..."`, `"Alice does X"`), that character is Tier 1 + first in order, but every **other** participant was evaluated against Tier 1/2/3 normally. Specifically: if the named character's turn ends on a physical event landing on another participant's body (touch, contact, strike, gesture toward, addressed-by-name in dialogue), that other participant qualifies as Tier 1 "physically engaged" or "directly addressed" and MUST be in `turn_order`. A single-speaker `turn_order` is correct only when (a) `user_prompt` explicitly excludes others (`"Rosa-only"`, `"other characters stay silent"`), or (b) no other participant has a genuine reactive beat available.
- [ ] Output written to `infrastructure/dialogues/{dialogue_id}/reply_plan.json`
