---
name: Dialogue Writing Rules
description: Canonical formatting rules for all dialogue output — speech wrapping, action perspective, inline rules, paragraph breaks
type: domain
---

# Writing Rules — Dialogue Formatting

All dialogue output, whether generated replies or adapted opening lines, must follow these rules.

---

## Speech wrapping

| Content | Format |
|---|---|
| Spoken dialogue | `"double quotes"` |
| Physical actions / stage directions | `*asterisks*` |
| Interior thoughts | `` `backticks` `` |

Source lines with bare speech (no quotes) — add double quotes. Preserve all existing asterisk action beats.

---

## First-person action descriptions

Action descriptions are written in **first person** from the speaking character's perspective:

- Correct: `*I set the towel down.*`
- Wrong: `*She sets the towel down.*`

---

## Inline rules

Action and dialogue may appear on the same line:

```
*I set the towel down.* "I noticed you hadn't eaten."
```

Interior thoughts **always occupy their own line** — never inline with action beats or dialogue:

```
*I set the towel down.* "I noticed you hadn't eaten."

`Why is this so hard to say?`
```

---

## Paragraph breaks

Output is stored as a JSON string and rendered as markdown. Separate distinct paragraphs — action beats, dialogue exchanges, reaction beats, internal monologue blocks — with a blank line (`\n\n` in the JSON string) so they render as separate paragraphs.

**Do not collapse everything into a single block of text.** A reply or opening of any length should have multiple paragraphs.
