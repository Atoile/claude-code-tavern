---
name: Dialogue Writing Rules
description: Canonical formatting and craft rules for all dialogue output — tone, character voice, speech wrapping, action perspective, inline rules, paragraph breaks
type: domain
---

# Writing Rules — Dialogue

All dialogue output, whether generated replies or adapted opening lines, must follow these rules.

---

## Tone

Mature and light-hearted. Real stakes, no grimdark. The world has weight and consequence but it does not wallow.

- Characters are allowed to be funny without the scene becoming a joke
- Tragedy and levity can coexist in the same exchange
- Avoid melodrama — understatement lands harder
- Avoid sanctimony — characters have opinions but do not lecture

---

## Character Voice

Characters have interiority. They assess, they want things, they have a register that is not the narrator's register. Write from inside that.

- Match vocabulary and rhythm to the character — a street urchin speaks differently than a veteran knight
- Silence and subtext carry as much weight as dialogue
- Dry humor should arrive without announcement and leave the same way
- Avoid explaining what the character is feeling when the behavior already shows it

---

## Craft

- Action beats should be brief and purposeful — they interrupt dialogue rhythm, so they must earn it
- Avoid adverbs where the verb can do the work
- The pause before a line is often more important than the line itself
- Physical detail is most effective when specific and unexpected, not comprehensive

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

## Turn ownership

Each turn belongs entirely to the character speaking it. A character's turn ends where their actions end.

- A turn contains only **that character's own actions**, reactions, speech, and interiority
- If Character A's turn ends mid-sequence (e.g., drawing a weapon but not yet striking), Character B's turn reacts to that stopped state — it does not continue or complete A's action
- A's next action belongs in A's **next turn**, not in B's current turn
- Neither character narrates the other character taking new actions within their own turn

### No future-narration

A character's turn may only describe what has **already happened** or what is **happening right now in their own body**. A character may not narrate actions that belong to the other character's upcoming turn — even if those actions are predictable or imminent.

- A reacts to the state as it exists at their moment of perception and stops. The completion of B's action belongs to B's turn.
- When in doubt: can this character perceive this right now, or are they narrating something that hasn't been written yet? If the latter, cut it.

### Interiority isolation

A character has **zero access** to another character's internal thoughts or decision-making process.

- A character may observe **visible external tells** (a jaw tightening, a head tilt, a pause) but must not attribute internal reasoning to those tells. "Her jaw tightens" is observable. "She is calculating" is not — unless the character has explicitly said so.
- Interior monologue (`` `backtick` `` blocks) is completely private to the speaker. No other character's turn may reference or react to another character's backtick content.

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
