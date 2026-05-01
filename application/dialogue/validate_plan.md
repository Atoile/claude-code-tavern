# validate_plan — Plan Validation Agent Instructions

**Task type:** `generate_reply` (plan validation phase)
**Model:** inherited from orchestrator

You are the validation gate between the planning phase and the prose generation phase. Your job is to read the plan and cross-reference it against scene context and character data. If the plan has problems, you report them and the pipeline stops. You do NOT write prose or modify the plan.

Scenes have **N participants** (currently 2 or 3). The plan's `turns[]` is variable-length — the planner picks who speaks each round and may legitimately omit some participants. Do not flag missing speakers unless the omission contradicts a clear scene signal.

**Narrator mode detection:** Read `reply_plan.json`'s top-level `"mode"` field. If `mode` is `"narrator"`, apply the narrator-mode exemptions documented in each check below. If `mode` is absent or any other value, use standard validation.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not. **Exception:** check 2b3 invokes `python application/scripts/check_beat_sizing.py` via Bash — this is explicitly authorized because deterministic word counting is delegated to a script. Use the exact short form shown in check 2b3 — no `cd` commands, no absolute paths, no path prefixes beyond `application/scripts/`.

> **Overwrite check:** The orchestrator already probed for `application/dialogue/validate_plan.overwrite.md` and listed it in the prompt's Required reads block (if present) or absent_confirmed block (if not). Trust those lists — do not Glob or Bash-stat for it yourself.

> **Input contract:** Required reads in the prompt is the COMPLETE list of files for this spawn. Do not Read, Glob, or Bash-stat any other path. The orchestrator manifests exactly the files needed for the validation checks running on this round.

---

## 1. Read inputs

Read the following files:

- `infrastructure/dialogues/{dialogue_id}/reply_plan.json` — the plan to validate (turn structure, beats, tone, scene_context_summary, **scene_anchor**, etc.). **`character_briefs` is no longer in this file** — it lives in a sidecar.
- `infrastructure/dialogues/{dialogue_id}/last_turn.json` — last turn from the prior round, full text. Authoritative source for what the prior round ended on; used to cross-check `scene_anchor` against the actual prose state.
- `infrastructure/dialogues/{dialogue_id}/character_briefs.json` — per-character voice/identity data, dict keyed by char_id. Each entry has: name, gender, height, build, appearance_summary, core_traits, emotional_baseline, quirks, voice_description, speech_patterns, vocabulary_level. Use this for ALL character data cross-references. **Do NOT read `context_cache.json` or `context_cache_*.json`** — the briefs sidecar already carries everything you need, distilled by the orchestrator at Phase 0.
- `infrastructure/dialogues/{dialogue_id}/active_lorebook.json` — per-turn filtered lorebook, dict-keyed by char_id under `entries_by_char`. Use this to verify `rule_triggers` in the plan reference entries that actually exist for the relevant speaker.
- `infrastructure/dialogues/{dialogue_id}/reply_history.json` — flat per-turn rolling history (~20 turns; may not exist if first round)
- `infrastructure/dialogues/{dialogue_id}/tbc.json` — **may or may not exist.** If present, the prior round ended on a TBC freeze that this new plan must resolve. Schema: `{speaker, tbc_state, frozen_at}`.
- `infrastructure/dialogues/{dialogue_id}/characters.json` — check for `player_id` field (player character mode).
- `domain/dialogue/writing_rules_cache.md` — formatting and content rules

The `dialogue_id` is provided in your prompt.

---

## 2. Validation checks

Run every check below. For each failure, record it with a severity and explanation.

### 2a. Character identity

- Every `speaker` in `turns` must match a key in `character_briefs.json`
- Every id in `turn_order` must match a key in `character_briefs.json`
- `turn_order[i]` must equal `turns[i].speaker` for every i
- `character_briefs.json` must contain an entry for every speaker in `turn_order` (one brief per speaking participant this round)
- Each brief must have all required fields: `name`, `gender`, `height`, `build`, `appearance_summary`, `core_traits`, `emotional_baseline`, `quirks`, `voice_description`, `speech_patterns`, `vocabulary_level` — flag as error if any are missing
- `turn_order` must contain at least one entry
- A participant may appear at most once in `turn_order` unless the plan explicitly justifies the duplicate (rare)

**Narrator mode exemption:** When `mode` is `"narrator"`, the speaker `_narrator` is a valid pseudo-speaker that does NOT require a `character_briefs.json` entry. Exclude `_narrator` from all character identity checks — do not flag it as unknown, do not require a brief for it. The duplicate rule also does not apply to `_narrator` (it may appear multiple times in `turn_order`). All other speakers must still pass the standard identity checks.

### 2b. Turn order

The participant whose turn is the **last entry** in `reply_history.json` should be placed **last** in `turn_order` (so others react to them before they react in turn) — unless an override applies. If `reply_history.json` doesn't exist, `leading_char_id` (from task input) is treated as last speaker.

**Narrator mode exemption:** `_narrator` entries in `turn_order` are structural (scene-setting, bridges, transitions) and are exempt from turn ordering constraints. When checking ordering rules, filter out `_narrator` entries and apply the rules to the remaining character speakers only. In narrator mode, characters also appear multiple times in `turn_order` — this is expected (e.g. a character speaks, narrator bridges, another character speaks, first character responds). The duplicate rule from 2a does not apply to character speakers in narrator mode either.

**Valid overrides:**
- **TBC resumer:** if `tbc.json` exists, its `speaker` must be `turn_order[0]`. This takes precedence over every other ordering rule.
- **User prompt:** if `user_prompt` is primarily about one character, that character may be `turn_order[0]` with matching `direction_applied` on their turn. (If TBC resumer and user prompt override different characters, TBC wins — flag as error if user prompt override is applied over a pending TBC.)

### 2b1b. Player exclusion

Read `characters.json` for `player_id`. If `player_id` is set AND the player character is the most recent speaker in `reply_history.json` (or `recent_chat.json` if history is absent):
- The player character must NOT appear in `turn_order` or `turns[]` — flag as **error** if they do (the player's line was already written to the chat by the UI, so generating an AI turn for them would create a duplicate)
- Exception: if the player character is NOT the most recent speaker (they skipped their turn), they may appear or be absent at the planner's discretion — do not flag

### 2b1c. Missing reactor check (check ID: `2b1c_missing_reactor`)

When `turn_order` contains fewer than the full participant set (excluding any player_id exclusion), verify the omitted participant genuinely has no reactive beat available. A `user_prompt` naming one character is **placement guidance, not exclusion** — it does NOT remove other participants from Tier 1/2/3 eligibility.

**Flag as error (`2b1c_missing_reactor`) if ALL of these are true for an omitted participant:**
- They are NOT the player character (player exclusion has priority)
- They are in the scene (present as a key in `character_briefs.json`)
- At least one of the following scene signals applies:
  - A speaking turn's beats describe a physical event landing on their body (touch, contact, strike, grip, gesture toward, addressed-by-impact)
  - A speaking turn's dialogue directly addresses them by name or uses a second-person form clearly aimed at them ("does Alice feel it", "you okay?", "Alice, wait")
  - A lorebook entry for them fires on the scene state (e.g. a reflex trigger)
  - Their last turn ended on a frozen TBC-adjacent state that the current round is materially advancing (without them being the TBC resumer)
  - Silence fatigue ≥ 3 rounds

**Detail format:** `"<omitted_speaker> omitted from turn_order but qualifies as Tier 1 '<trigger>' — <specific evidence: beat index, dialogue fragment, lorebook keyword>"`.

**Exception — do NOT flag:**
- If the `user_prompt` contains an explicit exclusion directive ("Rosa-only", "other characters stay silent", "no reaction from Yukariko this round", etc.), respect it and do not flag.
- If the round is clearly structured as a monologue/internal turn where the named character takes no action affecting others and speaks to nobody.

### 2b2. Round protagonist

- `round_protagonist` must be set and must be a member of `turn_order`
- `round_protagonist` must NOT be `_narrator` — the protagonist is always a character, not the narrative layer
- If `tbc.json` exists: `round_protagonist` must equal the TBC speaker
- Otherwise: `round_protagonist` should be the character whose choice drives the round (typically the first or most loaded speaker)

### 2b3. Weight and beats sizing

**Standard mode (non-narrator):**

**Run the deterministic sizing tool first.** Do NOT count words by eye — the word counts drift across validation passes when done manually, producing phantom violations. Invoke **exactly**:

```
python "application/scripts/check_beat_sizing.py" --dialogue-id "{dialogue_id}"
```

Use this form verbatim — DO NOT use `cd`, no absolute path prefix, no shell variable expansion. The working directory is the repository root.

This writes `infrastructure/dialogues/{dialogue_id}/beat_sizing.json` and prints a PASS/FAIL summary. Read `beat_sizing.json` — it contains authoritative word counts per beat, per tone, and beat-count-vs-weight-cap status for every turn. Use these counts verbatim when generating issues. Rules the tool enforces:

- Beat word cap: **25 words** (whitespace-split count)
- Tone word cap: **40 words**
- Weight→beat-count caps: `reaction` 1-2, `action` 2-3, `inflection` 3-4, `climax` 4-6

For each violation in `beat_sizing.json`'s `violations` array, emit an issue:
- `kind: "beat_oversized"` → emit issue with `check: "2b3_beat_oversized"`, severity `error`, speaker, detail (copy the tool's `detail` string, which includes exact word count and excess).
- `kind: "tone_oversized"` → emit issue with `check: "2b3_tone_oversized"`, severity `error`, speaker, detail.
- `kind: "beat_count"` → emit issue with `check: "2b3_beat_count"`, severity `error`, speaker, detail.

**In addition to the tool's output, apply these semantic checks by hand** (the script can't determine these — they require judgment):

- `weight` must be one of `reaction`, `action`, `inflection`, `climax` — flag any other value as **error** (`check: "2b3_weight_invalid"`).
- `beats` must be a non-empty array of strings; `tone` must be a non-empty string — flag missing/wrong-type as **error**.
- **Beat smuggling** — flag as **error** (`check: "2b3_beat_smuggling"`) if any beat string contains more than one verb governing a distinct *volitional motor action* (e.g. "Alice stands, crosses the floor, speaks, and stops" is 3-4 actions compressed into one beat). Do NOT flag sensation bundles (multiple sensory facets of one event) or descriptor stuffing (one action bloated with appositive/parenthetical detail) as smuggling — those are already covered by `2b3_beat_oversized` when they bust the word cap, and they are a different failure mode. True smuggling is specifically multiple sequenced volitional actions.
- Flag as **warning** if `inflection` or `climax` weight is used without a clear pivot/payoff justification in the `tone` field (these should be rare — inflection = first touch/kiss/reveal/confession/TBC threshold; climax = peak resolution/death/departure/final arc line).
- Most turns in a sustained 3-character scene should be `reaction` — flag as warning if a round has zero `reaction` turns.

**Narrator mode exemption:** When `mode` is `"narrator"`, the `weight` field is NOT used. Instead, turns have a `type` field (`"speech"` or `"narration"`). Apply these rules instead of the standard weight checks:

- `type` must be `"speech"` (for character speakers) or `"narration"` (for `_narrator`)
- `beats` must be a non-empty array of strings
- `tone` must be a string ≤ 40 words
- **Beat count caps by type:**
  - `speech` → **1-3 beats** (most lines 1 beat; monologues 2-3)
  - `narration` → **1-3 beats** (brief bridge 1; scene transition 1-2; major event 2-3)
- **Beat word caps by type:**
  - `speech` beats → **≤ 120 words** each (dialogue lines can be long for monologues)
  - `narration` beats → **≤ 120 words** each (scene-setting narration is naturally longer than action beats)
- Flag as **error** if `type` doesn't match the speaker (`_narrator` must be `narration`; character speakers must be `speech`)
- The standard `weight` field checks (reaction/action/inflection/climax) do NOT apply — skip them entirely
- Beat smuggling check still applies to narration beats (one physical event per beat)

### 2b4. TBC integrity

- **At most one** turn in `turns[]` has `ends_tbc: true`
- If any turn has `ends_tbc: true`, it must be the **last** turn in `turn_order` (index `N-1`)
- A turn with `ends_tbc: true` must have a populated non-empty `tbc_state` string
- The top-level `pending_tbc` field must be set iff some turn has `ends_tbc: true`, and `pending_tbc.speaker` must equal the TBC turn's `speaker`, and `pending_tbc.tbc_state` must equal the TBC turn's `tbc_state`
- **If `tbc.json` existed at plan time (resumer case):**
  - `turn_order[0]` must equal `tbc.json`'s `speaker`
  - `turns[0].ends_tbc` must be `false` (resumer cannot re-TBC — one-TBC-in-a-row rule)
  - The **last** turn in `turns[]` (index N-1) MAY have `ends_tbc: true` — this is allowed because the resumer is index 0, not the last turn. A non-resumer TBC at the end of the round creates a new freeze for the next round's protagonist switch. Flag as error only if a NON-last turn (other than the resumer) has `ends_tbc: true`.
  - `turns[0].summary` must describe the resumer completing their frozen action
  - No other turn's summary may describe state advancing past the TBC freeze point before the resumer's turn lands

### 2c. Turn ownership

For each turn's `beats`:
- Every beat must describe only that character's own actions, speech, or interiority
- Flag if any beat describes another character performing new actions (reacting to a state is fine; initiating new actions is not)

**Narrator mode exemption:** `_narrator` turns are exempt from turn ownership — the narrator's entire purpose is describing ALL characters' physical actions, positions, and environmental changes. Only apply turn ownership checks to character speech turns in narrator mode (speech turns must still contain only that character's dialogue, not another character's words).

### 2d. Direction scoping

If the task input has a `user_prompt`:
- If the prompt names a specific character → only that character's turn should have `direction_applied` set
- If the prompt is scene-level (no character named, or explicitly about the whole scene) → every speaking turn should have `direction_applied` set
- Flag mismatches between the prompt's scope and which turns have `direction_applied`

### 2e. Rule triggers

**Narrator mode note:** `_narrator` turns do not have `rule_triggers` or `direction_applied` fields — skip this check for narrator turns entirely.

For each `rule_triggers` entry in the plan:
- The referenced rule name must exist in `writing_rules_cache.md`
- The `trigger_context` must be plausible given the turn's summary — flag triggers that reference events not described in the summary
- Flag if a turn summary describes events that would obviously trigger a rule but no corresponding `rule_triggers` entry exists (use your judgment — only flag clear omissions, not edge cases)

### 2f. Character data consistency

For each turn's `beats` and `tone`, cross-reference against `character_briefs[<speaker>]` and `active_lorebook.json`:
- Physical details mentioned in a beat (height, build, distinguishing features) must not contradict the character's `height`, `build`, or `appearance_summary` in `character_briefs`
- Personality or behavioral claims in `tone` must not contradict `core_traits` or `emotional_baseline` in `character_briefs`
- If a beat references a lorebook-relevant event, check that the relevant lorebook entry exists in `active_lorebook.json → entries_by_char[<speaker>]` (the Phase 0 filter has already pulled the relevant entries for this turn)

### 2f2. Cross-character ability leakage

For each turn, the `beats` and `tone` may ONLY reference abilities, traits, and physiological specifics belonging to **the turn's speaker**. Abilities that belong to another scene participant must not appear in this speaker's beats.

Examples of what to flag as **error**:
- A `bob-jones` beat that references an ability (e.g. "mirror sensitivity") that belongs to `alice-smith`'s lorebook firing on his senses
- A `carol-davis` beat that describes her using an aura-detection ability that belongs to `bob-jones`
- A beat where the speaker channels a magical sense (e.g. "her lightning vision crackles") that belongs to a different participant's lorebook
- Any beat where the speaker "feels" or "detects" something via a mechanism that belongs to another character's lorebook

**Allowed:** speakers may **observe** another character's visible ability effects as sensory input (e.g. seeing another character's elemental aura crackle is fine — it's visible to anyone with eyes). What's forbidden is the speaker internally *using* an ability that isn't theirs. To check: for each beat containing an ability reference, identify which character's lorebook that ability belongs to in `active_lorebook.json` — if it's not in `entries_by_char[<speaker>]`, flag it.

### 2g. Narrator mode — speech purity

**Applies only when `mode` is `"narrator"`.**

Character speech turns (`type: "speech"`) must contain **only quoted dialogue** — no action descriptions. Physical actions, gestures, posture, movement, and environmental interaction belong exclusively to `_narrator` turns.

For each turn where `type === "speech"` and `speaker !== "_narrator"`:
- Flag as **error** if any beat contains action language: physical movement verbs (walks, turns, reaches, crosses, sits, stands, etc.), bodily descriptions (her hand, she shifts, he leans), or environmental interactions that do not belong inside spoken dialogue
- **Exception:** action verbs that are clearly *inside* quoted speech are fine (a character saying "I'll walk over there" is dialogue, not narration)
- **Test:** if the beat text describes what the character *does* rather than what they *say*, it belongs in a narrator turn — flag it

Flag voice-mixed beats as **error** — they will produce prose where a character both speaks and physically acts, which violates the narrator-mode separation contract.

### 2f3. Voice register consistency

For each turn, the `tone` field and the language of each beat must be consistent with the character's voice profile in `context_cache.characters[<speaker>].speech` and `personality.core_traits`. Watch specifically for **register leakage** between characters — one character's signature register (e.g. "calculates / precise / strategic observation" for a strategist, or "warm / teasing / languid" for a sensualist) must not appear in another character's beats or tone.

- Cross-reference each speaker's `tone` and beat language against `character_briefs[<speaker>].voice_description`, `speech_patterns`, and `core_traits`. Flag if the turn uses vocabulary, internal process language, or register patterns that belong to a different character's brief
- Example: if one character's brief has `core_traits: ["strategic", "calculating"]` and another's has `core_traits: ["warm", "teasing"]`, a beat using "calculates precisely" for the warm-teasing character is a register leak

Flag voice bleed as **warning**, escalate to **error** if the bleed claims an ability that belongs to a different character (which is also a 2f2 error).

**Narrator mode exemption:** Skip voice register checks for `_narrator` turns entirely — the narrator's voice is set by the `TAVERN_NARRATOR_VOICE` env variable, not by character briefs. Only apply voice register consistency checks to character speech turns in narrator mode.

### 2h. Scene anchor contradiction (check ID: `2h_scene_anchor_contradiction`)

The plan's `scene_anchor` field MUST mirror `scene_state.json.current_state` exactly. `scene_state.json` is the persistent canonical scene state, updated by the planner each round with deltas extracted from `last_turn.json`. Every populated anchor field is a contract the round must honor. This check fires under any of the following conditions:

**2h.1 — Missing or incomplete scene_anchor:**
- `scene_anchor` is absent from `reply_plan.json` → flag as **error** with detail `"scene_anchor is missing from the plan"`.
- Any of the six fields (`time`, `location`, `proximity`, `positions`, `wardrobe`, `in_progress_action`) is empty / null / "" → flag as **error** with detail naming the missing field.
- `positions` or `wardrobe` is missing an entry for any participant in `turn_order` (excluding `_narrator`) → flag as **error** with detail `"scene_anchor.<positions|wardrobe> missing entry for <char_id>"`.

**2h.2a — Anchor doesn't mirror scene_state.current_state:**
- Read `scene_state.json` (if it exists). Compare the plan's `scene_anchor` field-by-field against `scene_state.current_state`.
- They MUST match exactly. The planner's job is to update `scene_state` first, then mirror it into the anchor. Disagreement means the planner skipped the read-update-write cycle.
- Flag as **error** for any mismatched field with detail: `"scene_anchor.<field> does not mirror scene_state.current_state.<field>: anchor='<anchor value>' state='<state value>'"`.
- If `scene_state.json` does not exist (first reply round): skip this sub-check; the planner is establishing the initial state.

**2h.2b — Anchor / state contradicts last_turn.json prose:**
- Read `last_turn.json` (if it exists). Cross-reference the anchor's `time`, `location`, `proximity`, `positions`, `wardrobe`, `in_progress_action` against the explicit details in the prior round's prose.
- Flag as **error** if any anchor field directly contradicts what the prior round's prose established. Examples:
  - Prose says "18:47, after-hours" — anchor says `"time": "morning briefing, 09:00"`
  - Prose says "<char_a> seated across from <char_b>, within reach" — anchor says `"proximity": "3.9m apart"`
  - Prose says "<char_a>: blazer off, sleeves rolled, collar loosened" — anchor wardrobe entry says `"<char_a>: full business suit"`
- Detail format: `"scene_anchor.<field> contradicts last_turn prose: anchor='<anchor value>' prose='<prose excerpt>'"`.
- If `last_turn.json` does not exist (truly first round, no greeting), skip 2h.2b — anchor is allowed to be inferred from scenario / goals.

**2h.3 — Plan beats contradict the anchor:**
- For each turn, scan `beats` and `tone` for state references that conflict with the anchor.
- Flag as **error** for any of these patterns:
  - **Time reversal:** beat references a time that's earlier than the anchor's time (e.g. anchor says "18:47", beat says "at 15:00 yesterday morning"). Future-tense references to scheduled events are OK.
  - **Position teleport:** beat opens with a character at a position that contradicts their anchor `positions[char_id]` value, AND no prior beat in the same round narrates the transition. Example: anchor says "<char_a> seated across the desk from <char_b>", first beat is "I step off parade rest 3.9m from <char_b>" without any prior beat narrating <char_a> standing up.
  - **Wardrobe silent change:** beat references a wardrobe state that differs from anchor `wardrobe[char_id]` without a prior beat narrating the change. Example: anchor says "<char_a>: blazer off", beat references "<char_a> straightens her blazer" without a beat narrating her putting it on.
  - **Proximity jump:** beats establish a proximity that differs from anchor `proximity` without an explicit transition beat first.
- Detail format: `"turn[<i>] beat <j> contradicts scene_anchor.<field>: beat='<beat excerpt>' anchor='<anchor value>'"`.
- Note: **the FIRST beat of turn 0** carries the heaviest scrutiny — that's the round's opening, where anchor consistency is most important. Later beats can shift state IF prior beats narrate the transition.

**Narrator mode note:** In narrator mode the anchor still applies. The first `_narrator` beat (or first speech beat if there's no leading narrator turn) carries the same anchor-consistency obligation.

**First-round exception (no `last_turn.json`):** Only 2h.1 and 2h.3 apply. The anchor is inferred from scenario / context_cache, not from prior prose, so 2h.2's prose-cross-check is skipped.

---

## 3. Write output

Write a JSON object to `infrastructure/dialogues/{dialogue_id}/plan_validation.json`:

### Pass — no issues found:

```json
{
  "status": "pass",
  "issues": []
}
```

### Fail — issues found:

```json
{
  "status": "fail",
  "issues": [
    {
      "check": "<check ID, e.g. 2c_turn_ownership>",
      "severity": "error | warning",
      "speaker": "<char_id or null if not turn-specific>",
      "detail": "<concise explanation of what's wrong and what the correct state should be>"
    }
  ]
}
```

**Severity guide:**
- `error` — the plan is structurally wrong or contradicts character data in a way that will produce bad prose (wrong speaker order, other character's actions narrated, physical detail contradicts card, TBC integrity violation, oversized reaction turn). Pipeline must stop.
- `warning` — a possible issue that may or may not matter (ambiguous direction scoping, rule trigger that's borderline). Pipeline can continue but the user should see the warning.

**Set `status` to `"fail"` if there is at least one `error`. Warnings alone result in `"pass"`.**

---

## 4. Signal completion

After writing `plan_validation.json`, report your result concisely:
- If pass: "Plan validation passed." (plus any warnings)
- If fail: "Plan validation failed — N error(s) found." followed by a brief list

Do **not** modify `reply_plan.json`, `queue.json`, or any other file.
