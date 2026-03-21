# Character Aggregate — `data.json` Schema

Canonical shape of a repacked character file at `infrastructure/characters/{id}/data.json`.

> **Overwrite:** If `domain/character/schema.overwrite.md` exists, read it alongside this file — it defines additional fields that extend this base schema.

All fields must be populated. Use `null` only when a value genuinely cannot be inferred from source material.

---

## Top-level sections

```
meta
identity
appearance
personality
speech
behavior
abilities
voice_archetype
dialogue_seeds
lorebook
scenario_defaults
filter_tags
```

---

## `meta`

| Field | Type | Notes |
|---|---|---|
| `name` | string | Display name |
| `id` | string | Slug: lowercase, hyphens |
| `source_card` | string | Original PNG filename |
| `repacked_at` | string | ISO 8601 timestamp |

---

## `identity`

| Field | Type | Notes |
|---|---|---|
| `full_name` | string | |
| `aliases` | string[] | Nicknames, titles, alternate names |
| `age` | string \| number | Exact or approximate |
| `gender` | string | |
| `species` | string | human, elf, etc. |
| `occupation` | string \| string[] | |
| `background_summary` | string | 2–3 sentence core backstory |

---

## `appearance`

| Field | Type | Notes |
|---|---|---|
| `summary` | string | Concise physical description, SDXL-friendly |
| `height` | string | In cm, e.g. `"165 cm"`. Never null — estimate if not stated. |
| `build` | string | Body type |
| `hair` | string | Color, length, style |
| `eyes` | string | Color, notable features |
| `skin` | string | Tone, notable features |
| `distinguishing_features` | string[] | Scars, tattoos, horns, etc. |
| `typical_clothing` | string | Default outfit |

---

## `personality`

| Field | Type | Notes |
|---|---|---|
| `core_traits` | string[] | 5–8 dominant traits as short phrases |
| `strengths` | string[] | Positive traits and capabilities |
| `flaws` | string[] | Weaknesses, vices, blind spots |
| `values` | string[] | What they care about most |
| `fears` | string[] | Fears and insecurities |
| `quirks` | string[] | Behavioral habits, tics, signature gestures |
| `mbti_approximation` | string \| null | e.g. `"ENFP (The Campaigner)"` — always include archetype label |
| `emotional_baseline` | string | Default emotional state and temperament |

---

## `speech`

| Field | Type | Notes |
|---|---|---|
| `voice_description` | string | Tone, pace, volume, accent |
| `vocabulary_level` | string | `crude` / `casual` / `educated` / `formal` / `archaic` |
| `speech_patterns` | string[] | Contractions, pet phrases, verbal tics |
| `sample_lines` | string[] | 3–5 characteristic lines that capture their voice |
| `languages` | string[] | Languages spoken, if mentioned |

---

## `behavior`

| Field | Type | Notes |
|---|---|---|
| `social_style` | string | Default interaction mode |
| `relationship_defaults.strangers` | string | |
| `relationship_defaults.friends` | string | |
| `relationship_defaults.romantic` | string | |
| `relationship_defaults.authority` | string | |
| `relationship_defaults.subordinates` | string | |
| `triggers` | string[] | Things that provoke strong reactions |
| `comfort_behaviors` | string[] | What they do when relaxed or happy |
| `stress_behaviors` | string[] | What they do under pressure |

---

## `abilities`

| Field | Type | Notes |
|---|---|---|
| `skills` | string[] | Combat, magic, craft, social skills |
| `powers` | string[] \| null | Supernatural abilities if any |
| `limitations` | string[] | Weaknesses, power restrictions |

---

## `voice_archetype`

| Field | Type | Notes |
|---|---|---|
| `suggested_role` | string | `warrior` / `scholar` / `clergy` / `merchant` / `noble` / `commoner` |
| `personality_axis` | string | e.g. `"dominant-warm-playful"` |
| `age_tier` | string | `young` / `mature` / `elder` |
| `archetype_tag` | string | Combined tag e.g. `"noble-dominant-warm-mature"` |

---

## `dialogue_seeds`

| Field | Type | Notes |
|---|---|---|
| `greeting` | string | Default opening line for a scene |
| `alternate_greetings` | string[] | Alternative opening lines |
| `example_dialogues` | string[] | Exchanges demonstrating character voice |

---

## `lorebook`

Array of lore entries:

```json
{
  "keys": ["trigger keywords"],
  "content": "string — lore entry text",
  "priority": number
}
```

If the source lorebook has 20+ entries, keep only those directly relevant to this character's personality and relationships.

---

## `scenario_defaults`

| Field | Type | Notes |
|---|---|---|
| `preferred_setting` | string \| null | Typical environment |
| `typical_scenario` | string \| null | Default scene premise. Written for a generic "the other character" / "you" — adapted per-pairing by the dialogue context. |

---

## `filter_tags`

`string[]` — copied verbatim from the raw card's `tags` field, then:
- Deduplicated (case-insensitive, keep first occurrence)
- Gender tag ensured: `female` or `male`
- Dominance tag ensured: `dominant`, `submissive`, `switch`, `dominant-leaning`, or `submissive-leaning`
