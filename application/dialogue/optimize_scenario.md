# optimize_scenario — Sonnet Agent Instructions

**Task type:** `optimize_scenario`
**Model:** `claude-sonnet-4-6`

You are given a queue item. Execute it completely. Do not modify `infrastructure/queue/queue.json` — the orchestrator handles all queue state.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/optimize_scenario.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

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

For 2-participant scenes, "the other character" → the one other participant.
For 3+-participant scenes, "the other character" → all the other participants together (e.g. for a scene with Alice, Bob, and Carol, Alice's scenario adapts to feature both Bob and Carol as her counterparts; Bob's adapts for Alice and Carol; etc.).

**Rules — minimal changes only:**
- Replace generic "the other character" / "you" → the other participants' name(s)
- Fix gender pronouns or anatomical assumptions that don't match the other participants' `data.json`
- Fix role assumptions (e.g. "middle-aged" if the other character is young) that clearly don't fit
- Do NOT rewrite from scratch, invent new hooks, or add embellishment
- Preserve the original wording and structure everywhere that still fits
- For 3+-participant scenes where the source scenario is 1-on-1 framed, you may make minimal additions to acknowledge that more than one person is present (e.g. "Alice walks in" → "Alice and Bob walk in together"). Do not invent group dynamics not implied by the source.

---

## 4. Adapt each character's opening lines

Each character has a `dialogue_seeds.greeting` (always 1) and `dialogue_seeds.alternate_greetings` (array, may be empty). Adapt every one. **Never invent new lines — one output entry per source line.**

**What to change:**
- Third-person references to "the other character" → other participants' names or correct pronouns
- Wrong gender pronouns for the other participants
- Situational details about the other participants that don't fit their actual identity
- **Third-person narrator POV for the speaker themselves** — some source cards write the speaker's own actions in third person throughout: `"She steps out from behind the counter"`, `"Her hand leads the way"`, `"Rosy has been watching her partner"`. These are not references to the other character — they are the speaker being narrated from outside. Convert every such line to first person: `"I step out from behind the counter"`, `"My hand leads the way"`, `"I've been watching her"`. This is a full POV conversion, not a pronoun swap. Do it systematically for every action beat and narration line in the opening, even if most of the opening is in this style.

**What NOT to change:**
- Direct address ("you," "your") — this is the speaker addressing the other participant(s) and stays as "you" (or "you both" if a 3+ scene and the line clearly addresses everyone)
- The character's own voice, vocabulary, rhythm, action beats
- The hook, emotional register, and intent of the line
- **Setting words, world-flavor markers, environmental nouns, or any vocabulary that is part of the speaker's own voice/setting** — apartment/hardwood/refrigerator, temple/silk/lantern, bridge/console/airlock, whatever the source uses. These belong to the character's data, not to this task.
- **Scenario framing** — the *kind* of scene the source sets up: wedding, spouse summoned, established lover, captive, visiting dignitary, long-estranged rival, morning-after, interrogation, bedchamber reconciliation, banquet-in-honor-of, etc. This is a source-authored premise, not a contradiction to resolve.

---

**Core principle — change WHO, never WHAT KIND:**

You are changing **who** the scene is with. You are never changing **what kind of scene it is**.

If the source says "wedding banquet," the output is a wedding banquet with the new partner as the spouse. If the source says "my spouse stood against me in council," the output is "my spouse stood against me in council" with the new partner as the spouse. If the source says "captive kneeling in my solar," the output is a captive kneeling in the solar. The adapter's job is pronoun/name/anatomy swaps — **not premise arbitration**.

This holds even when the resulting pairing requires an implicit AU to make sense. "Princess Beatrice of Alvea has been arranged as Queen Miranda's political spouse" is a perfectly legitimate AU for a wedding-banquet greeting, even if the two characters' lorebooks treat each other as rivals. The user chose this pairing knowing what was in both source files — they are inhabiting the AU deliberately. Your job is to deliver it, not to second-guess it.

---

**Anti-pattern 1 — stripping scenario framing because it "doesn't fit":**

If the source greeting is a wedding banquet and the new partner is a rival queen, **do NOT** dissolve the wedding into a generic "state banquet" because rivals don't marry. Keep the wedding. Swap the bride. Swap the pronouns. Done.

If the source greeting is "my spouse opposed me in council" and the new partner is a visiting royal, **do NOT** rewrite it as "a guest was discourteous to their host." Keep the spousal opposition. Swap the spouse.

If the source greeting is "my established lover summoned to my bedchamber" and the new partner is an enemy, **do NOT** downgrade it to "adversary I have decided to seduce." Keep the lover framing. Swap the lover.

The symptom of this anti-pattern: the output's scenario is *weaker* or *vaguer* than the source's. If you find yourself generalizing "wedding" → "state occasion," "spouse" → "guest," "lover" → "visitor," stop and put it back.

---

**Anti-pattern 2 — fixing setting/world details:**

If you notice that the character's source greetings contain setting/world details that seem to clash with their identity (e.g. "this character is described as ancient but the greeting is set in a modern apartment", or "this character is described as a starship captain but their greeting is in a tavern"), **do NOT fix it here**. Do not soften "apartment" to "rooms" because the character is ancient. Do not change "key in the lock" to "step at the door" because the character feels mythic. Do not pick world-flavor on the character's behalf.

Two reasons:
1. The user may have *intentionally* written an urban-fantasy / historical-fantasy / etc. setting where the apparent contradiction is the point. Long-lived supernatural beings living in modern apartments is a valid setting; you should not "resolve" it.
2. Even if the contradiction is unintentional, fixing it per-pairing means every future scenario for this character will get a different drift. The fix belongs in the source `data.json`, not in `scenario.json`.

---

**What to do instead (both anti-patterns):** complete the task with minimal partner-adaptation only (pronouns, partner name, anatomical/role assumptions about the *other* character), and **flag the observation in your task report** so the user can fix the source if they want to.

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
  }
}
```

Every participant from `input.participants` must appear as a key in the output `participants` dict. Each one needs a `scenario` and an `openings` array regardless of which will be the leading character — that choice happens later in the UI.

No markdown fences, no trailing commentary. Valid JSON only.

---

## 6. Validate before writing

- [ ] Every input participant has a key in the output `participants` dict
- [ ] Each scenario is a minimal adaptation — original wording mostly intact, only target-specific references changed
- [ ] Openings use "you/your" for direct address, not the other participants' names
- [ ] Every opening traces to a source line — no invented lines
- [ ] All speech in `"double quotes"`, all actions in `*asterisks*`, all interior thoughts in `` `backticks` ``
- [ ] Action descriptions written in first person (`*I reach for the caddy.*`, not `*She reaches for the caddy.*`). If a source card is written entirely in third-person narrator style for the speaker, every single action line must be converted — not just ones that mention "the other character".
- [ ] Interior thoughts always on their own line — never inline with action beats or dialogue
- [ ] Distinct paragraphs separated by blank lines (markdown-ready formatting)
- [ ] Pronouns for the other participants match their actual gender(s)
- [ ] Valid JSON, no markdown wrapping

---

## 7. Write characters.json

Write `infrastructure/dialogues/{dialogue_id}/characters.json`:

```json
{
  "participants": {
    "<char_id>": {
      "id": "<directory id>",
      "name": "<display name>",
      "data_path": "<infrastructure/characters/{id}/data.json>"
    }
  }
}
```

The `id` must be the **directory name** (e.g. `alice-smith`), not the `meta.id` inside `data.json`. The frontend uses directory names to look up characters. Note: do **not** write `leading_id` here — that gets set later when the user picks the leading character in the UI.

---

## 8. Signal completion

After writing both output files, your work is done. Queue state is managed by the orchestrator.
