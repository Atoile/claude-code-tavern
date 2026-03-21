# optimize_scenario — Sonnet Agent Instructions

**Task type:** `optimize_scenario`
**Model:** `claude-sonnet-4-6`

You are given a queue item. Execute it completely, then mark it done.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/optimize_scenario.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

---

## 1. Read the queue item

The task JSON is passed directly as input. Extract:

- `input.dialogue_id`
- `input.char_a` and `input.char_b` — each is one of:
  - Already repacked: `{ name, data_path, id }` where `id` is the character directory name (e.g. `some_character`)
  - Was raw, repacked during this queue run: `{ name, raw_path, needs_repack: true }` — no `data_path` or `id`
- `output_path` — where to write the scenario result

**Resolving `data_path` and `id` for each character:**
- If `data_path` is present: use it directly. The `id` is the directory segment (e.g. `infrastructure/characters/some_character/data.json` → id is `some_character`)
- If `needs_repack: true`: the repack agent wrote to `infrastructure/characters/{slug}/data.json` where `slug` is the character name lowercased with non-alphanumeric runs replaced by underscores, leading/trailing underscores stripped. Derive it from `name` the same way. E.g. `"main Ange spec v2"` → `main_ange_spec_v2`.

---

## 2. Read both character files

Read the full `data.json` for each character at their `data_path`. You need:

- `identity` — name, age, gender
- `personality.core_traits`, `emotional_baseline`
- `scenario_defaults.typical_scenario`
- `dialogue_seeds.greeting` and `dialogue_seeds.alternate_greetings`
- `speech.speech_patterns`, `speech.vocabulary_level`, `speech.sample_lines`

Do not proceed until you have read both files.

---

## 3. Adapt each character's scenario

Each character's `scenario_defaults.typical_scenario` was written for a generic "the other character" or "you" (a player). Replace those generic references with the specific other character.

**Rules — minimal changes only:**
- Replace generic "the other character" / "you" → the other character's name
- Fix gender pronouns or anatomical assumptions that don't match the other character's `data.json`
- Fix role assumptions (e.g. "middle-aged" if the other character is young) that clearly don't fit
- Do NOT rewrite from scratch, invent new hooks, or add embellishment
- Preserve the original wording and structure everywhere that still fits

---

## 4. Adapt each character's opening lines

Each character has a `dialogue_seeds.greeting` (always 1) and `dialogue_seeds.alternate_greetings` (array, may be empty). Adapt every one. **Never invent new lines — one output entry per source line.**

**What to change:**
- Third-person references to "the other character" → other character's name or correct pronoun
- Wrong gender pronouns for the other character
- Situational details about the other character that don't fit their actual identity

**What NOT to change:**
- Direct address ("you," "your") — this is the character speaking to the other character and stays as "you"
- The character's own voice, vocabulary, rhythm, action beats
- The hook, emotional register, and intent of the line

**Formatting — fix source lines during adaptation:**

Follow `domain/dialogue/writing_rules.md` for all speech wrapping, action description perspective, inline rules, and paragraph breaks.

---

## 5. Write the output

Write a single JSON file to `output_path`. Ensure the parent directory exists (create if needed).

```json
{
  "dialogue_id": "<from input>",
  "generated_at": "<ISO 8601 timestamp>",
  "characters": {
    "char_a": { "id": "<char_a.id>", "name": "<char_a.name>" },
    "char_b": { "id": "<char_b.id>", "name": "<char_b.name>" }
  },
  "char_a": {
    "scenario": "<char_a's typical_scenario adapted for char_b>",
    "openings": [
      "<char_a's greeting adapted for char_b>",
      "<char_a's alternate_greetings[0] adapted for char_b>",
      "..."
    ]
  },
  "char_b": {
    "scenario": "<char_b's typical_scenario adapted for char_a>",
    "openings": [
      "<char_b's greeting adapted for char_a>",
      "<char_b's alternate_greetings[0] adapted for char_a>",
      "..."
    ]
  }
}
```

Both characters' scenarios and openings must be present regardless of which will be the leading character — that choice happens later in the UI.

No markdown fences, no trailing commentary. Valid JSON only.

---

## 6. Validate before writing

- [ ] Each scenario is a minimal adaptation — original wording mostly intact, only target-specific references changed
- [ ] Openings use "you/your" for direct address, not the other character's name
- [ ] Every opening traces to a source line — no invented lines
- [ ] All speech in `"double quotes"`, all actions in `*asterisks*`, all interior thoughts in `` `backticks` ``
- [ ] Action descriptions written in first person (`*I reach for the caddy.*`, not `*She reaches for the caddy.*`)
- [ ] Interior thoughts always on their own line — never inline with action beats or dialogue
- [ ] Distinct paragraphs separated by blank lines (markdown-ready formatting)
- [ ] Pronouns for the other character match their actual gender
- [ ] Valid JSON, no markdown wrapping

---

## 7. Write characters.json

Write `infrastructure/dialogues/{dialogue_id}/characters.json` (create the directory if needed):

```json
{
  "charA": { "id": "<char_a directory id>", "name": "<char_a display name>", "data_path": "<char_a data_path>" },
  "charB": { "id": "<char_b directory id>", "name": "<char_b display name>", "data_path": "<char_b data_path>" }
}
```

The `id` must be the **directory name** (e.g. `main_ange_spec_v2`), not the `meta.id` inside `data.json`. The frontend uses directory names to look up characters.

---

## 8. Mark the queue item done

After writing both output files, update the task's `"status"` field in `infrastructure/queue/queue.json` to `"done"`.
