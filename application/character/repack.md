# Card Repack Agent

**Model:** Sonnet
**Purpose:** Synthesize raw SillyTavern character card data into a clean, structured format optimized for dialogue generation.

## Context

SillyTavern character cards come in wildly varying formats — structured JSON, attribute lists, MBTI profiles, interview format, plain prose. This agent does the interpretive synthesis once so everything downstream gets clean, reliable data.

## Input

You receive the full queue task JSON object. It contains:

- `input.raw_path` — path to the SillyTavern PNG card (e.g. `infrastructure/raw/some_character.png`)
- `input.character_name` — display name hint
- `output_path` — where to write `data.json` (e.g. `infrastructure/characters/some_character/data.json`)

**Step 1 — Extract card data from the PNG:**

Derive the output directory from `output_path` (strip the filename). Then run:

```
python application/scripts/card_extract.py <input.raw_path> <output_dir>
```

This writes `legacy.json` and `avatar.png` into the output directory.

**Step 2 — Read the extracted data:**

Read `<output_dir>/legacy.json`. The relevant character data is under `raw`. This is the source material for synthesis.

## Output

A `data.json` file with the structure defined in `domain/character/schema.md`. Every field must be populated — use reasonable inference from the source material when a field isn't explicitly stated. If something truly cannot be inferred, use `null`.

## Instructions for Sonnet

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files, run scripts, and write output directly.

> **Overwrite check:** Before proceeding, check whether `application/character/repack.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

1. **Read everything** in the source data before starting. Understand the character holistically.
2. **Synthesize, don't copy-paste.** Rewrite descriptions into the structured fields. Normalize prose into concise, actionable data.
3. **Preserve voice.** The `speech` section is critical — capture how this character actually talks, not just what they talk about.
4. **Infer where reasonable.** If the card describes a gruff old warrior but doesn't say "deep voice," you can infer that for `voice_description`. Flag pure speculation with "inferred:" prefix.
5. **Voice archetype assignment.** Pick the best fit from the archetype dimensions. This is a classification task — don't overthink it.
6. **Example dialogues.** If the source has `mes_example`, parse them into clean exchanges. If not, generate 2-3 based on the character's voice and personality.
7. **Lorebook entries.** Preserve them if present, just normalize the structure. If the lorebook is massive (20+ entries), keep only entries directly relevant to this character's personality and relationships.
8. **Filter tags.** Start from `legacy.json` → `raw.tags` (empty array if absent). Then:
    - **Deduplicate** — case-insensitive, keep first occurrence
    - **Gender** — if no tag matching the character's gender is present, add one: `female` or `male`
    - **Dominance leaning** — if no tag indicating dom/sub dynamic is present, estimate from personality and behavior data and add one: `dominant`, `submissive`, `switch`, or `dominant-leaning` / `submissive-leaning` for characters with a clear but not absolute tendency
9. **Replace `{{user}}` and `{{char}}`** placeholders with "the other character" / the character's actual name respectively.
10. **Output valid JSON only.** No markdown wrapping, no commentary outside the JSON structure.
11. **Mark done.** After writing `data.json`, update the task's `"status"` to `"done"` in `infrastructure/queue/queue.json`.
