# optimize_scenario — Sonnet Agent Instructions

**Task type:** `optimize_scenario`
**Model:** `claude-sonnet-4-6`

You are given a queue item. Execute it completely. Do not modify `infrastructure/queue/queue.json` — the orchestrator handles all queue state.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not.

> **Overwrite check:** The orchestrator already probed for `application/dialogue/optimize_scenario.overwrite.md` and listed it in the prompt's Required reads block (if present) or absent_confirmed block (if not). Trust those lists — do not Glob or Bash-stat for it yourself.

> **Input contract:** Required reads in the prompt is the COMPLETE list of files for this spawn. Do not Read, Glob, or Bash-stat any other path beyond what's listed there or what the numbered steps below explicitly call out (the participant `data.json` files).

> **Thinking discipline — strict, applies inside thinking blocks too.** Empirically, the previous gentle phrasing of this rule has been ignored. Read the prohibitions below as binding.
>
> **Prohibited inside thinking blocks (these are wasted tokens AND degrade output quality):**
> - **Drafting adapted opening prose.** Sentences like *"I'm depicting Hana at the counter when the door chimes, looking up to see Horan walk in..."* or *"I pat the mattress beside me, letting my tail curl hopefully..."* or *"I'm pressing her against the wall, my tail securing her hip..."* belong inside the `Write` call's JSON, not in thinking. The source greetings are already in your context — transform them directly into the output, do not pre-compose them in thinking.
> - **Restating or paraphrasing source greetings** before transforming them. The greeting text is in `data.json` which you've already read. Quoting/paraphrasing it back to yourself in thinking adds nothing. Read it, decide what to swap, write the swap.
> - **Process narration.** *"Now I'm working through..."*, *"I'm continuing with..."*, *"Let me check..."*, *"Now I'm moving into..."* — all forbidden. Decide and emit, do not announce yourself.
> - **Iterative prose refinement.** *"Let me revise..."*, *"I'm settling on..."*, *"That's tighter."* — if you find yourself revising, write the first version and exit. Validator + downstream usage will catch real issues; thinking-side polish is mostly waste.
> - **Accumulating notes in thinking instead of in the `notes` array.** Anti-pattern flags, world-flavor mismatches, source-data inconsistencies, unresolved tokens — write each one as one entry in the `notes` array directly when you spot it. Do NOT pile them up in thinking and then transcribe to `notes` at the end.
> - **Re-checking the same character data multiple times.** Decide what each opening needs once, then write. Returning to "let me check Horan's voice again" or "let me re-verify Hana's wardrobe" three times is loop behaviour.
>
> **Permitted inside thinking blocks (terminal decisions only):**
> - Which lines need POV conversion (third-person speaker → first person)
> - Which pronouns/names to swap and where
> - Which `{token}` patterns need resolving and to what value
> - Which anomalies to flag in the `notes` array (not the contents of the note — just *that* a note is needed; the actual note text goes straight into the JSON)
> - Whether a flagged item is anti-pattern 1 (scenario framing weakening) vs anti-pattern 2 (world/setting drift) — if applicable

---

## 1. Read the queue item

The task JSON is passed directly as input. Extract:

- `input.dialogue_id`
- `input.participants` — an array of 2 or more participant entries. Each entry is one of:
  - Already repacked: `{ id, name, data_path }` where `id` is the character directory name (e.g. `alice-smith`)
  - Was raw, repacked during this queue run: `{ id, name, raw_path, needs_repack: true }` — `id` is pre-derived by the frontend via `name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')`. The repack agent will have written `data.json` to `infrastructure/characters/{id}/data.json` by the time you run.
- `output_path` — where to write the scenario result

**Resolving `data_path`:**
- If `data_path` is present in the queue input: use it directly.
- If `needs_repack: true`: read from `infrastructure/characters/{id}/data.json` (the repack agent writes there).

---

## 2. Read every participant's character file

Read the full `data.json` for each participant. You need from each:

- `identity` — name, age, gender
- `personality.core_traits`, `emotional_baseline`
- `scenario_defaults.typical_scenario`
- `dialogue_seeds.greeting` and `dialogue_seeds.alternate_greetings`
- `speech.speech_patterns`, `speech.vocabulary_level`, `speech.sample_lines`

Do not proceed until you have read every file.

---

## 3. Adapt each character's scenario

Each character's `scenario_defaults.typical_scenario` was written for a generic "the other character" or "you" (a player). Replace those generic references with the **other participants** of this scene.

"The other character" → the one other participant.

**Rules — minimal changes only:**
- Replace generic "the other character" / "you" → the other participant's name
- Fix gender pronouns or anatomical assumptions that don't match the other participant's `data.json`
- Fix role assumptions (e.g. "middle-aged" if the other character is young) that clearly don't fit
- Do NOT rewrite from scratch, invent new hooks, or add embellishment
- Preserve the original wording and structure everywhere that still fits

If the scene has 3+ participants, see the addendum at the end of this file before proceeding.

---

## 4. Adapt each character's opening lines

Each character has a `dialogue_seeds.greeting` (always 1) and `dialogue_seeds.alternate_greetings` (array, may be empty). Adapt every one. **Never invent new lines — one output entry per source line.**

**What to change:**
- Third-person references to "the other character" → other participant's name or correct pronouns
- Wrong gender pronouns for the other participant
- Situational details about the other participant that don't fit their actual identity
- **Third-person narrator POV for the speaker themselves** — some source cards write the speaker's own actions in third person throughout: `"She steps out from behind the counter"`, `"Her hand leads the way"`, `"Rosy has been watching her partner"`. These are not references to the other character — they are the speaker being narrated from outside. Convert every such line to first person: `"I step out from behind the counter"`, `"My hand leads the way"`, `"I've been watching her"`. This is a full POV conversion, not a pronoun swap. Do it systematically for every action beat and narration line in the opening, even if most of the opening is in this style.

**What NOT to change:**
- Direct address ("you," "your") — speaker addressing the other participant; stays as "you"
- The character's own voice, vocabulary, rhythm, action beats
- The hook, emotional register, and intent of the line
- **Setting words, world-flavor markers, environmental nouns, or any vocabulary that is part of the speaker's own voice/setting** — apartment/hardwood/refrigerator, temple/silk/lantern, bridge/console/airlock, whatever the source uses. These belong to the character's data, not to this task.
- **Scenario framing** — the *kind* of scene the source sets up: wedding, spouse summoned, established lover, captive, visiting dignitary, long-estranged rival, morning-after, interrogation, bedchamber reconciliation, banquet-in-honor-of, etc. This is a source-authored premise, not a contradiction to resolve.

---

**Core principle — change WHO, never WHAT KIND.** You are changing **who** the scene is with, never **what kind of scene it is**. Pronoun/name/anatomy swaps only — not premise arbitration. Implicit AUs are fine; the user chose the pairing deliberately.

**Anti-pattern 1 — never weaken scenario framing.** Wedding → "state banquet," spouse → "guest," lover → "visitor," captive → "adversary I'm seducing" are all wrong. Keep the kind of scene; swap who's in it. Symptom: your output is *weaker* or *vaguer* than the source. If so, put it back.

**Anti-pattern 2 — never fix world/setting drift.** If a card's setting clashes with its identity (ancient being + modern apartment, mythic figure + casual diction), do not soften vocabulary or pick world-flavor on the character's behalf. The user may have written it that way intentionally; even if not, the fix belongs in source `data.json`, not per-pairing.

**What to do instead (both anti-patterns):** apply only minimal partner-adaptation (pronouns, partner name, anatomical/role assumptions about the *other* character), and add an entry to the output `notes` array so the user can fix the source if they want to.

**Formatting — fix source lines during adaptation:**

Follow `domain/dialogue/writing_rules_cache.md` for all speech wrapping, action description perspective, inline rules, and paragraph breaks. The cache is the pre-merged (baseline + `*.overwrite.md`) authoritative source at runtime. If it is missing, run `python application/scripts/build_writing_rules_cache.py` to build it before proceeding.

---

## 5. Write the scenario output

Write a single JSON file to `output_path`.

```json
{
  "dialogue_id": "<from input>",
  "generated_at": "<ISO 8601 timestamp>",
  "participants": {
    "<char_id>": {
      "name": "<display name>",
      "scenario": "<this character's typical_scenario adapted for the other participants>",
      "openings": [
        "<this character's greeting adapted for the other participants>",
        "<this character's alternate_greetings[0] adapted for the other participants>",
        "..."
      ]
    }
  },
  "notes": [
    "<observation string — anti-pattern flags, source-data inconsistencies, unresolved tokens, etc.>"
  ]
}
```

Every participant from `input.participants` must appear as a key in the output `participants` dict. Each one needs a `scenario` and an `openings` array regardless of which will be the leading character — that choice happens later in the UI.

The `notes` array is the **report channel** for anything you want to surface to the user without modifying the adapted prose:
- Anti-pattern observations ("Saki's greeting 1 references Hana's mother — does not match Hana's barista background")
- Unresolved `{token}`s in source text (when defined by overwrite)
- Speaker-self tokens you intentionally left unresolved
- Source-card inconsistencies you noticed but did not fix

If you have nothing to flag, emit an empty array `"notes": []`. Always include the field.

No markdown fences, no trailing commentary outside the JSON. Valid JSON only.

---

## 6. Validate before writing

- [ ] Every input participant has a key in the output `participants` dict
- [ ] `notes` field present (empty array if nothing to flag)
- [ ] Every opening traces to a source line — no invented lines
- [ ] Valid JSON, no markdown wrapping

---

## 7. Signal completion

The orchestrator pre-creates the dialogue directory and writes the initial `characters.json` with the participants dict in deterministic Python before spawning you. Your only output is the scenario file at `output_path`. Do NOT mkdir, do NOT write `characters.json`, do NOT touch any other file. Queue state is managed by the orchestrator.

---

## Addendum — 3+ participants (skip if only 2)

This section applies only when `input.participants.length >= 3`. For 2-participant scenes, ignore everything below.

**Section 3 (scenario adaptation):** "The other character" → all the other participants together. For a scene with Alice, Bob, and Carol: Alice's scenario adapts to feature both Bob and Carol as her counterparts; Bob's adapts for Alice and Carol; etc. Where the source scenario is 1-on-1 framed, you may make minimal additions to acknowledge that more than one person is present (e.g. "Alice walks in" → "Alice and Bob walk in together"). Do not invent group dynamics not implied by the source.

**Section 4 (opening adaptation):** Direct address ("you," "your") may become "you both" / "you all" if the line clearly addresses everyone. Otherwise keep "you" as-is.
