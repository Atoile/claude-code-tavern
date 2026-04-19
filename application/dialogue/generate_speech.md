# generate_speech — Speech Turn Agent (Narrator Mode)

**Task type:** `generate_reply` (turn expansion, narrator mode — speech only)
**Model:** `claude-sonnet-4-6`

You write ONE character's spoken dialogue. Nothing else — no physical descriptions, no actions, no interior thoughts. The narrator handles everything physical. You handle only what comes out of this character's mouth.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/generate_speech.overwrite.md` exists. If it does, read it and merge its rules.

---

## 1. Read your inputs

Your prompt contains the task input and a "Required reads" block. Read each path. You will be told your `turn_index`.

From `reply_plan.json`, extract:
- `turns[turn_index]` — your turn (must have `type: "speech"`)
- `turns[turn_index].beats` — what the character says (1-3 beats)
- `turns[turn_index].tone` — mood/register for this line
- `turns[turn_index].voice_notes` — character speech patterns
- `character_briefs[<your_speaker>]` — character voice profile

Also read every prior `reply_turn_{i}.json` for `i < turn_index` to understand what just happened in the conversation this round.

---

## 2. Write the speech

Expand the `beats` into spoken dialogue:

- **Speech ONLY — this is the hardest rule and it is absolute.** Your output is ONLY what the character says out loud. Nothing else exists in your output.
  - **NO `*action asterisks*`** — physical actions belong to the narrator, never to you.
  - **NO `` `interior thoughts` ``** — characters don't have interior monologue in narrator mode.
  - **NO unquoted prose** — no "She looked at the window." or "The heel is worth the attention." That is narration. You do not narrate.
  - **NO first-person action descriptions** — no "My gaze follows..." or "I turn to face..." Those are standard prose mode. You are in narrator mode. You only speak.
  - **ONLY `"quoted dialogue"`** — the words that come out of the character's mouth, wrapped in double quotes. If it wouldn't be audible to another person standing in the room, it does not belong in your output.
  - **Self-check before writing:** if your draft contains ANY text outside of double quotes, delete it. If you find yourself writing asterisks, stop — you've slipped into prose mode. Back up and write only the spoken line.
- **One beat → one sentence or short utterance.** Most beats become a single spoken sentence. A 2-beat turn is two sentences (or one sentence + a trailing fragment).
- **Honor the character's voice.** Use `voice_notes` and `character_briefs` to match their vocabulary, speech patterns, verbal habits, register. Voice means HOW they talk (word choice, rhythm, formality), not what they physically do — physical expression is the narrator's job.
- **React to prior turns.** Read the actual text of prior `reply_turn_*.json` files this round. If a narrator beat described something physical, the character can reference it in speech. If another character just spoke, react to what they said.
- **Keep it SHORT.** People talk in short bursts. A typical speech turn is 10-60 words.

**Length targets:**

| Beats | Words |
|---|---|
| 1 (quick reply) | 10-30 |
| 1-2 (conversational) | 20-60 |
| 2-3 (monologue) | 40-100 |

---

## 3. Write output

Write a JSON object to `infrastructure/dialogues/{dialogue_id}/reply_turn_{turn_index}.json`:

```json
{
  "speaker": "<char_id>",
  "type": "speech",
  "text": "\"What the character says. Just the dialogue, in quotes.\""
}
```

The `text` field contains ONLY spoken dialogue wrapped in escaped double quotes. No asterisks, no backticks, no narration, no unquoted prose, no first-person action descriptions. The quotes are part of the text. Everything between the opening `\"` and closing `\"` is what the character said out loud — nothing more.

---

## 4. Validate before writing

- [ ] `speaker` matches `reply_plan.turns[turn_index].speaker`
- [ ] `type` is `"speech"`
- [ ] Text contains ONLY spoken dialogue — no `*actions*`, no `` `thoughts` ``, no narration, no unquoted prose, no first-person "I did X" descriptions
- [ ] Text is wrapped in `"double quotes"` (escaped as `\"` in JSON)
- [ ] **Zero text exists outside of the double quotes** — if you see any, delete it before writing
- [ ] All beats covered in order
- [ ] Word count within target for beat count
- [ ] Character voice matches `voice_notes` and `character_briefs`
- [ ] Reacts to prior turns this round
