# Create Character From Scratch

**Purpose:** Standards for manually building a `data.json` when no SillyTavern PNG exists — synthesized directly from source knowledge (fictional character, original concept, etc.) plus any user-specified additions.

> **Overwrite check:** Before proceeding, check whether `application/character/create_from_scratch.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions and take precedence where they conflict.

---

## General principles

1. **Synthesize, don't list.** Write fields as clean, actionable data — not raw bullet dumps. Personality, speech, and behavior fields should be usable directly by a dialogue agent.
2. **Infer where reasonable.** If the source material implies something without stating it, make the inference and prefix with `"inferred:"` only if it's speculative.
3. **All fields must be populated.** Use `null` only when a value genuinely cannot be inferred.
4. **Preserve voice.** The `speech` section is the most important section for dialogue quality — capture how the character actually talks.
5. **Write the output directory** as `infrastructure/characters/{id}/` using a slug derived from the character's name.

---

## Greetings — mandatory standards

Greetings for manually created characters must be **expansive and descriptive** — full scene-openers, not one-liners. Each greeting should stand alone as a usable scene start.

### `greeting` (default)

- Fully expands on `scenario_defaults.typical_scenario`
- Multi-paragraph: establishes setting, character's presence, mood, then a spoken line
- The other character has just arrived; this character is already present
- Uses writing_rules.md formatting throughout: `"speech"`, `*actions*`, `` `interior thoughts` ``

### `alternate_greetings`

Provide at least two alternate greetings:

- **Alternate 1** — near future: assumes some prior contact or familiarity. The characters have met; something has shifted since.
- **Alternate 2** — different setting or dynamic: variety in scenario, tone, or time elapsed.

Each alternate greeting is equally expansive — same multi-paragraph standard as the default.

---

## Writing rules reference

All greeting and dialogue content follows `domain/dialogue/writing_rules.md`:

- Spoken dialogue → `"double quotes"`
- Physical actions → `*asterisks*`
- Interior thoughts → `` `backticks` `` (always their own line, never inline)
- Separate paragraphs with blank lines (`\n\n` in JSON strings)
