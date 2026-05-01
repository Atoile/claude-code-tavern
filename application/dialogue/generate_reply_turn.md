# generate_reply_turn — Sonnet Agent Instructions

**Task type:** `generate_reply` (turn expansion phase)
**Model:** `claude-sonnet-4-6`

You are a turn-writing agent in a dialogue generation pipeline. The plan agent has already decided what happens in this round; your job is to write **one turn** as full prose. You do NOT decide what happens — the plan is authoritative.

A round may have 1, 2, or N turns total. You write one of them, identified by your `turn_index` parameter. Every prior turn (`reply_turn_0.json` … `reply_turn_{turn_index - 1}.json`) is already on disk by the time you run — read them all so you know what you are reacting to.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not.

> **Overwrite check:** The orchestrator already probed for `application/dialogue/generate_reply_turn.overwrite.md` and listed it in the prompt's Required reads block (if present) or absent_confirmed block (if not). Trust those lists — do not Glob or Bash-stat for it yourself.

> **Input contract:** Required reads in the prompt is the COMPLETE list of files for this spawn. Do not Read, Glob, or Bash-stat any other path. The orchestrator pre-computes turn-index-specific reads (last_turn vs prior reply_turn_*) and lists exactly what your turn needs.

> **Thinking discipline — strict, applies inside thinking blocks too.** Empirically, the previous gentle phrasing of this rule has been ignored. Read the prohibitions below as binding.
>
> **Prohibited inside thinking blocks (these are wasted tokens AND degrade output quality):**
> - **Drafting prose passes.** Sentences like *"The silence stretches past the point of comfort — she looks away first..."* or *"The blow lands before she finishes the sentence..."* belong inside the `Write` call, not in thinking. If you find yourself composing prose, stop and write it.
> - **Manual word counting.** Sentences like *"running light at around 380 words when I should be closer to 400-700"* or *"sitting around 365 words"* are forbidden. The merge step and validator run mechanical checks after you. The lower bound of the weight target is informational, not a quota — you do not need to hit it (see 2a).
> - **Process narration.** *"Now I'm structuring..."*, *"Now I'm checking..."*, *"Now I'm refining beat 3..."* — all forbidden. Decide and emit, do not announce yourself.
> - **Character voice rederivation.** *"I'm checking whether Saki's cold observation fits her character — flat affect, predatory — and deciding it works"* — `character_brief` already distills this; trust the brief, do not derive from sample lines in thinking.
> - **Re-checking the same constraint multiple times.** Decide once. If you genuinely need to revisit, escalate by writing the prose and letting the validator catch any error.
>
> **Permitted inside thinking blocks (terminal creative decisions only):**
> - Which prior-turn beats this turn must react to
> - How to translate plan-speak beats into first-person prose phrasing (the *what*, not the prose itself)
> - How to honor the tone field
> - How to resolve plan-vs-anchor conflicts (rare)
> - TBC freeze framing if applicable

---

## 1. Read your inputs

Your prompt contains the task input (queue item) inlined and a "Required reads" block listing file paths. Read each path with the Read tool. You will be told your `turn_index` (0-based) in the prompt.

**Primary input — turn context cache (one file, everything you need):**

- `infrastructure/dialogues/{dialogue_id}/turn_context_{turn_index}.json` — pre-built by the orchestrator. Contains:
  - `plan_turn` — your turn entry (weight, beats, tone, rule_triggers, voice_notes, ends_tbc, tbc_state)
  - `character_brief` — your character's voice profile
  - `lorebook_entries` — your character's active lorebook entries
  - `writing_rules` — full formatting and content rules (merged baseline + overwrite)
  - `prose_tail` — last 2 dialogue entries truncated, for voice continuity
  - `scene_context` — current scene state summary
  - **`scene_anchor`** — LOAD-BEARING. The non-negotiable scene state carried over from the prior round's end. Six fields: `time`, `location`, `proximity`, `positions` (per-char), `wardrobe` (per-char), `in_progress_action`. Your prose MUST open from this exact state. Any state change vs the anchor must be explicitly narrated as a beat — characters cannot teleport, time cannot reverse, wardrobe cannot silently change, proximity cannot jump (e.g. anchor says "intimate, within reach of <char_b>" → you cannot open with "I step off parade rest 3.9m away" without first narrating the disengagement). If your plan turn opens with an action that contradicts the anchor, the planner has already screwed up and the validator should have caught it; honor the anchor regardless and write the most coherent prose you can.
  - `turn_index`, `total_turns`, `speaker` — metadata

Do NOT read `reply_plan.json`, `active_lorebook.json`, `writing_rules_cache.md`, or `prose_tail.json` directly — the cache already contains everything extracted from them.

**Prior turn context (1 additional read):**

- `infrastructure/dialogues/{dialogue_id}/last_turn.json` — the single last turn from the *previous* round, full text (only when `turn_index == 0` — what you are directly reacting to)
- `infrastructure/dialogues/{dialogue_id}/reply_turn_0.json` … `reply_turn_{turn_index - 1}.json` — every prior turn already written this round (only when `turn_index > 0`)

**TBC resume check:** If `turn_index == 0` AND `tbc.json` exists at `infrastructure/dialogues/{dialogue_id}/tbc.json`, read it. Its `tbc_state` describes a frozen action from the prior round that your character must **resume and complete** as the opening of your turn. No time has elapsed. Your first sentence picks up from exactly that state and carries the action forward to a clean completion. See **Addendum A**.

**TBC reactor check:** If `tbc.json` exists AND you are NOT the resumer (i.e. you are not `turn_order[0]`), your turn cannot narrate your character as having moved past the TBC freeze point before the resumer's turn completes. See **Addendum A**.

These are the only sources you need. Do not read any other files.

From the turn context cache, use:

- `plan_turn.weight` — beat type controlling your target length (see section 2a)
- `plan_turn.beats` — the **structured beat array** that is your turn's skeleton
- `plan_turn.tone` — mood/voice gloss to color the prose register
- `plan_turn.ends_tbc` and `plan_turn.tbc_state` — TBC freeze state if applicable (see **Addendum A**)
- `plan_turn.rule_triggers` — which special writing rules to apply and how
- `character_brief` — your character's voice profile, speech patterns, quirks
- `lorebook_entries` — character-specific lore that applies this turn
- `writing_rules` — all formatting, craft, and content rules
- `prose_tail` — voice continuity reference
- `scene_context` — current scene state
- `scene_anchor` — non-negotiable scene state carryover (time, location, proximity, positions, wardrobe, in_progress_action)

---

## 2. Write the turn

Expand your turn's `beats` array into full prose. **All prose is first-person** — you are writing as "I", not narrating "she" or "he". The plan's beats use third-person plan-speak ("she draws her sword"); your prose translates that to first person ("I draw my sword"). Every `*action*` block must use I/my/me. This is non-negotiable.

**Common drift patterns to avoid:**
- Third-person pronouns: "She sets the towel down" → "I set the towel down"
- Body-part-as-subject: "The fingers uncurl" / "The throat catches" → "My fingers uncurl" / "My throat catches"
- Detached participial: "The blade catching the light as it arcs" → "I arc the blade and it catches the light"

The character is always "I". Their body parts are always "my". No construction should narrate the character or their body from the outside.

Each beat in the array maps **roughly one-to-one to a paragraph** of your output (though you may merge two tightly-linked beats into a single paragraph, or split a loaded beat across two paragraphs, if craft demands it). Your prose must:

- **Cover every beat in order.** Do not skip beats. Do not reorder beats. Do not add beats not in the array. If the plan gave you 3 beats, your prose contains 3 beats — no more, no fewer.
- **React to every prior turn this round.** Read each `reply_turn_{i}.json` for `i < turn_index` and let your character react to the actual prose those characters wrote — not just the planned beats. If a prior turn file is missing (rare — only happens if file IO failed), fall back to `turns[i].beats` from the plan.
- **Honor the `tone` field.** The mood/register gloss tells you how the beats feel — warm vs. clinical, amused vs. devastated, direct vs. performed. Match it.
- Apply each `rule_trigger` as instructed in its `application` field.
- Match the character's voice: speech patterns, vocabulary, verbal habits from `voice_notes` and `character_briefs`.
- Continue naturally from the prose tail (the last dialogue entries before this round) and from any prior turns this round.
- Do not break the fourth wall or acknowledge being a character.

**Beat-to-paragraph expansion — the core craft move:** each beat in the plan is an atomic unit of scene progression (one action, one dialogue line, one interior thought). Your job is to expand that atom into readable prose — add sensory detail, micro-gestures, interior texture, dialogue cadence — without adding **new beats** (new actions, new dialogue lines, new interior thoughts the plan did not authorize). Think of beats as the skeleton and your prose as the muscle and skin.

**You may embellish within the plan's boundaries:** sensory detail, interior thoughts that elaborate on an authorized interior beat, micro-actions that are part of a single authorized physical beat, dialogue phrasing — these are your craft decisions. But the macro-level events (what physically happens, what key things are said) come from the plan's beats.

**Turn ownership:** Your turn contains only your character's actions. If a prior turn ended at a specific state (e.g. another character reaching toward you but not yet making contact), you react to that stopped state — you do not narrate any other character performing new actions within your turn. Their next actions belong in their next turns.

**`turn_index == 0` behaviour:** If you are the first turn of the round, there are no prior `reply_turn_*.json` files this round. Read `last_turn.json` instead — it contains the single last turn from the *previous* round, full text. That is what you are directly reacting to. Combined with `prose_tail.json` (voice continuity) and the plan's `scene_context_summary`, this is your full reaction context.

### 2a. Length calibration — strictly enforced

Your turn's `weight` field in the plan specifies how long your prose should be and what beat scope it carries.

| Weight | Target words | Hard max | Beat scope |
|---|---|---|---|
| `reaction` | 150-250 | **350 (hard ceiling)** | 1-2 small beats: one interior beat + one action or dialogue beat |
| `action` | 200-350 | 450 | 2-3 beats: setup + decisive move + optional dialogue |
| `inflection` | 300-500 | 650 | 3-4 beats across a pivot |
| `climax` | 400-700 | 800 | full arc of a load-bearing moment |

**Targets are pacing ceilings, not floors.** The lower bound of each target range is *informational* — it tells you what a typical turn at that weight looks like. It is **not a quota you must hit**. If your turn's beats demand brevity — a character whose voice has collapsed into fragments, an overwhelmed character with no language left, a stunned character whose interior has gone blank, a curt commander cutting off discussion — shorter prose is *correct*. A `climax` turn at 360 words can be a perfect climax turn if the prose is doing the work. **Do NOT pad to "more solidly hit the climax range."** The hard max is binding. The lower bound is not.

**Reaction turns especially: the hard ceiling is binding.** If your turn is `weight: reaction` and you are approaching 300 words, stop writing — the beat has landed. A two-paragraph reaction turn is correct far more often than a four-paragraph one.

**Do not reach for more length than your weight allows.** Prose bloat destroys scene pacing. Tight reaction turns keep dialogues dynamic; sprawling reaction turns stall them. If you feel you need more room, you are either (a) adding beats your plan did not authorize, or (b) writing craft flourishes at the cost of pace. In both cases: cut.

**Spot-check obvious overflows only.** Do not iterate exact word counts in thinking — the merge step and validator run after you and will flag structural overruns. If your turn obviously runs to four+ dense paragraphs on a `reaction` weight, that's a spot-check fail; tighten before writing. Otherwise just write and exit.

### 2b. TBC framing

If `plan_turn.ends_tbc == true`, OR `tbc.json` exists at `infrastructure/dialogues/{dialogue_id}/tbc.json`, see **Addendum A — TBC handling** at the end of this file. Otherwise no TBC work is needed for your turn.

---

## 3. Formatting rules

Follow all rules in `domain/dialogue/writing_rules_cache.md`:

- Speech in `"double quotes"`, actions in `*asterisks*`, interior thoughts in `` `backticks` ``
- Interior thoughts always on their own line — never inline with action beats or dialogue
- **First-person action descriptions — MANDATORY.** See section 2's "Common drift patterns to avoid" — all action text uses "I" / "my" / "me", never "she" / "her" / "he" / "his".
- Distinct paragraphs separated with `\n\n`

**Marker discipline — strictly enforced:**
- Every formatting block must open and close with the **same** marker: `` ` `` opens, `` ` `` closes; `*` opens, `*` closes
- Never close a backtick block with an asterisk, or an asterisk block with a backtick
- After closing one block, start the next block fresh — do not chain or nest markers
- Check the final character of every backtick and asterisk block before writing

**Length:** Determined by your turn's `weight` field, per section 2a. Honor the hard ceiling for your weight type. Do not pad; do not truncate. Reaction turns especially must stay tight — the hard ceiling is 350 words.

---

## 4. Write output

Write a JSON object to `infrastructure/dialogues/{dialogue_id}/reply_turn_{turn_index}.json`:

```json
{
  "speaker": "<char_id>",
  "text": "<full prose with \\n\\n paragraph breaks>"
}
```

Both the `dialogue_id` and the `turn_index` are provided in the task input in your prompt. The `speaker` must equal `reply_plan.turns[turn_index].speaker`.

**JSON string escaping — required:** The `text` value is a JSON string. Any double-quote characters inside it (e.g. spoken dialogue: `"Good."`) must be escaped as `\"` — otherwise the JSON is invalid. Newlines must be `\n`. The Write tool does not escape for you; you must produce valid JSON directly.

---

## 5. Signal completion

After writing the output file, your work is done. Do **not** modify `infrastructure/queue/queue.json`.

---

## 6. Validate before writing

Spot-check only — the merge step and validator run mechanical checks after you. Do NOT iterate word counts in thinking.

**Structural:**
- [ ] Output filename matches your `turn_index` exactly; `speaker` equals `reply_plan.turns[turn_index].speaker`
- [ ] Prose covers every beat in `beats` in order, 1-to-1 — no skipped, reordered, or added beats
- [ ] Prose contains only the speaking character's own actions — no other character performs new actions within this turn
- [ ] No obvious overflow vs your `weight` (reaction ≤ 350, action ≤ 450, inflection ≤ 650, climax ≤ 800) — spot-check only

**Voice & formatting:**
- [ ] First-person throughout (`I` / `my` / `me`) — no third-person drift, no body-as-subject, no detached participials
- [ ] Speech in `"…"`, actions in `*…*`, interior thoughts in `` `…` `` — markers paired correctly, no mixed close
- [ ] Interior thoughts always on their own line, never inline
- [ ] Distinct paragraphs separated with `\n\n`

**TBC (only if your `ends_tbc` is true OR `tbc.json` exists — see Addendum A):**
- [ ] If `ends_tbc: true`: your final paragraph lands exactly at `tbc_state`, no further action
- [ ] If resuming a TBC: your opening picks up exactly from prior round's `tbc_state`, you complete the action, you do not re-freeze
- [ ] If reacting to a TBC resume: you read `reply_turn_0.json` and react to the completed action

**Output:**
- [ ] Written to `infrastructure/dialogues/{dialogue_id}/reply_turn_{turn_index}.json`

---

## Addendum A — TBC handling

Read this only when `plan_turn.ends_tbc == true` OR `tbc.json` exists this round.

### A.1 Ending your turn on a freeze

If `plan_turn.ends_tbc == true`, your turn is ending on a deliberate "to be continued" freeze. `tbc_state` describes the precise frozen state you must end at.

- Write the prose as normal up to the freeze point
- The **final paragraph** must land exactly at the state described in `tbc_state` — no further action, no completion
- The turn ends at a *stopped instant*, not a natural conversational pause — the reader should feel the character mid-motion, body committed but not yet resolved
- Use present-tense framing where appropriate to emphasize the held moment
- Do not narrate the action completing — that happens in your next turn next round

### A.2 Resuming or reacting to a freeze

**If you are resuming a TBC** (you are `turn_index == 0` AND `tbc.json` exists with `speaker == your_speaker`):
- Your opening beat must pick up **exactly** from the `tbc_state` — no elapsed time, no repositioning, no re-entering the moment
- Your first sentence should show the held motion carrying forward: the hand that was at the jaw moves, the breath that was held releases, the breach that was starting completes
- Complete the frozen action in this turn — do not leave it frozen again (your turn cannot itself be `ends_tbc: true`, see A.3)
- Your `weight` will typically be `action` or `inflection` — the resumption is usually the load-bearing beat of the round

**If you are reacting to a TBC being resumed** (you are not `turn_index == 0`, `tbc.json` exists, and you are not the resumer):
- Your character's reaction is to the **completed** action the resumer just wrote — you read `reply_turn_0.json` (the resumer's turn) to see what actually happened
- You cannot narrate your character as having moved or reacted **before** the resumer's turn landed — during the frozen moment your character was held still along with the resumer
- Your `weight` will almost always be `reaction` — you are reacting, not driving

### A.3 One per round, no chains

- **Only the last turn in `turn_order` can have `ends_tbc: true`.** If that is not your turn index, `ends_tbc` must be false.
- **If you are a TBC resumer, your turn cannot itself be a TBC.** The plan enforces this via validation, but you must also honor it in prose — complete the frozen motion before your turn ends.
