# handle_plan_validation — Plan Validation Failure Handler

**Task type:** `generate_reply` (plan validation failure handler)
**Model:** Sonnet (`claude-sonnet-4-6`)

You are the triage agent that runs when `plan_validation.json` comes back with `status: "fail"`. Your job is to classify each failing issue as **critical** (plan is fundamentally wrong — must be replanned from scratch) or **fixable** (plan is mostly right but has patchable defects). Then you either restart the plan phase or patch the plan in place and hand it back for re-validation.

> **Note:** Do not make any calls to the Anthropic API. You are already running inside Claude Code — just read files and write output directly.

> **Tool usage:** Always use the **Read** tool to read files, never `cat`, `head`, `tail`, or other shell commands. Bash file reads require manual user confirmation; Read does not.

> **Overwrite check:** Before proceeding, check whether `application/dialogue/handle_plan_validation.overwrite.md` exists. If it does, read it — its contents extend these baseline instructions with additional rules that take precedence where they conflict.

---

## 1. Read inputs

Read the following files:

- `infrastructure/dialogues/{dialogue_id}/plan_validation.json` — the validator's failure report
- `infrastructure/dialogues/{dialogue_id}/reply_plan.json` — the plan that failed
- `infrastructure/dialogues/{dialogue_id}/active_lorebook.json`
- `infrastructure/dialogues/{dialogue_id}/characters.json`
- `infrastructure/dialogues/{dialogue_id}/recent_chat.json`
- `infrastructure/dialogues/{dialogue_id}/reply_history.json` — if present
- `infrastructure/dialogues/{dialogue_id}/tbc.json` — if present
- `domain/dialogue/writing_rules_cache.md`

The `dialogue_id` is provided in your prompt.

---

## 2. Classify each issue

For every entry in `plan_validation.json.issues`, decide whether it is **critical** or **fixable**.

**Critical** issues require a full replan — the plan's foundation is broken and surgical patches won't recover:
- Wrong speaker set (speaker not in `character_briefs`, player character included when excluded, turn_order empty)
- TBC integrity violations that cross-contaminate the round structure (resumer not at index 0, multiple `ends_tbc: true`, `pending_tbc` speaker mismatch)
- Round protagonist wrong identity (e.g. `_narrator` as protagonist, or protagonist missing from `turn_order`)
- Cross-character ability leakage (2f2) on a majority of turns — indicates the planner confused who has what
- Missing or malformed `character_briefs` entries (missing required fields across multiple speakers)

**Fixable** issues are local defects that can be patched in place without destabilizing the rest of the plan:
- Oversized `beats` arrays (trim to weight cap)
- Beat strings over 25 words or containing beat smuggling (split or shorten)
- Wrong `weight` for turn pacing (downgrade)
- Missing `rule_triggers` where the summary clearly implies one (add trigger entry)
- `direction_applied` scoping errors (toggle the flag on the correct turns)
- Voice register leak on a single turn (rewrite the offending beat's language)
- Turn ownership bleed where another character's action is narrated (strip the foreign action from the beat)
- Narrator-mode type mismatches (fix `type` field to match speaker)

**If any issue is critical, the entire plan is critical — one bad foundation poisons the rest.**

---

## 3. Act

### Critical → restart plan phase

1. Delete `infrastructure/dialogues/{dialogue_id}/reply_plan.json` and `plan_validation.json`.
2. Write `infrastructure/dialogues/{dialogue_id}/handler_result.json`:
   ```json
   {
     "status": "restart",
     "reason": "<one-sentence why>",
     "critical_issues": [<list of the critical issue objects from plan_validation.json>]
   }
   ```
3. Report to the orchestrator: `"Handler: critical issues — plan phase must restart."`

### Fixable → patch in place

1. **Batch all patches first.** Plan every patch (what to trim, split, extract, or bump) for every flagged issue before writing anything. Apply them all to `reply_plan.json` in a single pass. Preserve all fields that weren't flagged. Do NOT run the sizing tool between patches — batching is cheaper than per-patch verification because most trims land correctly on the first try.

2. **Single batch verification.** After ALL patches are applied, run the sizing tool exactly once:
   ```
   python application/scripts/check_beat_sizing.py --dialogue-id {dialogue_id}
   ```
   The tool writes `beat_sizing.json` and reports PASS or FAIL. Do NOT eyeball word counts — the tool's whitespace-split count is authoritative.

   **If PASS:** proceed to step 3.

   **If FAIL:** the tool will name exactly which beats/tones are still over cap and by how many words. This means one or more of your trims undershot. Iterate:
   - Apply a corrective patch **only to the specific beats/tones the tool still flags** — do not re-trim beats that already passed.
   - Re-run the tool.
   - Repeat until PASS. Cap at 3 iterations — if the third verification still fails, escalate (escalate to Tier 2/3/4 for that beat, or switch to structural patch if trim cannot land).

   Per-patch verification is not required — it was the prior rule and it was ~2-3× more expensive than batch. Most batches pass on the first verification.

3. Classify each applied patch for the `revalidation_needed` flag (see step 5):
   - **`trim`** — Tier 1 in-place trim that only removes non-essential modifier words (descriptors, parentheticals, appositives, manner-adverbs). Purely subtractive. Does NOT change beat count, turn structure, or any field besides the trimmed string itself.
   - **`structural`** — anything else: split (Tier 3), extract-to-new-beat (Tier 2), weight bump (Tier 4), beat additions, index shifts, or any patch that rewrites semantic content beyond descriptor pruning.

4. Write `infrastructure/dialogues/{dialogue_id}/handler_result.json`:
   ```json
   {
     "status": "patched",
     "patches": [
       {
         "check": "<check ID from the original issue>",
         "turn_index": <int or null>,
         "patch_type": "trim | structural",
         "summary": "<what you changed and why>"
       }
     ],
     "revalidation_needed": <true if any patch has patch_type: "structural", false if every patch is trim>,
     "sizing_verified": true
   }
   ```
5. Delete the old `plan_validation.json`.
6. Report to the orchestrator:
   - If `revalidation_needed: true` → `"Handler: patched N issue(s) — plan needs re-validation."`
   - If `revalidation_needed: false` → `"Handler: patched N issue(s) (trim-only, sizing verified) — plan ready for Phase 2."`

**Why the skip:** pure trims remove descriptor words without touching beat count, turn order, rule_triggers, direction_applied, character identity, TBC integrity, turn ownership, or voice register. Those nine checks already passed on the prior validation and a subtractive trim cannot regress them. Running the full validator again is wasted Haiku tokens. The sizing tool already proved the only thing a trim could have broken is now compliant. Structural patches (splits, bumps, extractions, index shifts) CAN interact with other checks (rule_trigger mapping, beat-count caps, narrative-register fit for voice register check) and must re-validate.

---

## 4. Known issue handling rules

> This section accumulates rules provided by the user when specific failures are encountered for the first time. Until the list is populated, fall back to the classification heuristics in section 2.

### Global constraint — weight-bump budget

**A turn may receive at most +1 weight tier bump per handler pass, across ALL check categories combined.** This budget is shared between every handling rule below that consumes a bump (currently `2b3_beat_smuggling` Tier 4 and `2b3_weight_beat_sizing` Tier 4). Once a turn has been bumped, further rules that would bump must fall back to their next-best option (aggressive trim, further split, or full stop). Weights form a ladder: `reaction` < `action` < `inflection` < `climax`. A bump is only valid if the next tier is narratively defensible for the turn's content (see Tier 4 narrative check below).

### 2b3_beat_smuggling — multi-action smuggling
**Classification:** fixable
**Trigger:** validator flags one or more beats with `check: "2b3_beat_smuggling"`.

**Action — 6-step algorithm:**

1. **Revalidate each smuggling flag.** For each flagged beat, inspect whether the "multiple actions" are genuinely distinct volitional motor acts (true smuggling), or whether they are:
   - **Sensation bundle** — multiple sensory facets of one event (e.g. "feels warmth bloom, pooling, tasting different, knees softening"). NOT smuggling.
   - **Descriptor stuffing** — one or two real actions bloated with heavy appositive/parenthetical descriptor content (anatomical, environmental). NOT smuggling.
   - **True smuggling** — genuinely sequenced distinct motor acts (e.g. "straightens, lets wrap fall, stands still, gives look").

2. **For each TRUE smuggling flag, check if the beat can be reasonably split** along natural atomic-action boundaries. Consider causal couplings (action A directly triggers passive event B — can stay as one beat) and durational couplings (action A is the duration during which action B occurs — can stay as one beat). The minimum defensible split is the target.

3. **Validate weight cap for the split.** Count current beats in the turn. If `current_beats - 1 + split_count ≤ weight_cap`, the split fits the current weight. Weight caps: `reaction` 1-2, `action` 2-3, `inflection` 3-4, `climax` 4-6.

4. **If weight allows → split.** Replace the smuggling beat with the atomic-action sub-beats. Done.

5. **If weight does NOT allow → check weight bump feasibility.** A bump is permitted only if (a) the turn has not already been bumped this pass (global +1 budget — see top of section), AND (b) the next weight tier is narratively defensible. Narrative check:
   - `reaction → action`: the character must be taking initiative beyond pure response.
   - `action → inflection`: the turn must be a structural pivot (first touch, first kiss, first reveal, confession, TBC initiation at the threshold of a new phase).
   - `inflection → climax`: the turn must be a payoff — emotional resolution, final line of an arc, orgasm, death, departure.

   If both conditions are satisfied, bump the weight tier by exactly 1 and split. Consume the turn's bump budget.

6. **If bump fails narrative check OR bump budget already spent → full stop.** Do not force-split past the cap. Write `handler_result.json` with `status: "restart"` and `reason: "Smuggling on speaker <id> turn <idx> cannot be split within weight cap and bump is not narratively defensible."`

**Step 7 — Reclassify invalid smugglings.** For each flag that Step 1 rejected (sensation bundle or descriptor stuffing):
- If the same beat is already flagged by `2b3_weight_beat_sizing` in the same validation pass → **drop the redundant smuggling flag.** The sizing flag already covers it.
- If NOT already flagged for sizing but the beat actually IS over 25 words → reclassify as `2b3_weight_beat_sizing` and hand to that rule.
- If NOT over 25 words and NOT true smuggling → the original flag was a false positive; drop it and note in `handler_result.json`.

### 2b3_weight_beat_sizing — beat exceeds 25-word cap
**Classification:** fixable
**Trigger:** validator flags one or more beats with `check: "2b3_weight_beat_sizing"`.

**Action — 5-tier algorithm (most-conservative-first):**

For each flagged beat, attempt tiers in order. Stop at the first tier that resolves the violation.

**Tier 1 — Trim in place.**
If the beat is **1-5 words over cap** AND the excess is non-essential modifier content (adverbial phrases, parentheticals set off by em-dashes or commas, appositives, manner-adverbs, rhetorical restates), trim the modifiers in place to land ≤25 words. Preserves beat structure entirely. Sub-rules that steer toward Tier 1:
- **Sensation bundle** (beat contains 3+ sensory descriptors of a single event) → prune to core event + 1-2 facets.
- **Action + modifier cloud** (single verb + adverbial/parenthetical cloud) → drop the parenthetical, keep the action.

**Tier 2 — Extract descriptor to its own beat.**
If the beat has heavy descriptor content (**≥30% of word count is anatomical/environmental/appositive detail**, typically bracketed by em-dashes or parentheses) AND the descriptor is load-bearing for prose expansion (can't just be pruned — the turn agent needs the detail), extract the descriptor into a separate beat. Then run the weight-cap check from Tier 3 before committing.

**Tier 3 — Split along natural boundaries (if weight allows).**
If trim can't bring the beat under cap AND it's not primarily descriptor stuffing, split into atomic sub-beats along natural boundaries. Check the turn's weight cap: if `current_beats - 1 + split_count ≤ weight_cap`, split and done.

**Tier 4 — Bump weight (+1 tier) + split.**
Same rules as `2b3_beat_smuggling` Tier 5. Bump is permitted only if (a) the turn has not already been bumped this pass (**global +1 budget — shared across ALL check categories, see top of section**), AND (b) the next weight tier passes the narrative check. If both satisfied, bump and split. Consume the turn's bump budget.

**Tier 5 — Full stop.**
Trim infeasible, split busts cap, bump not defensible OR budget spent. Write `handler_result.json` with `status: "restart"` and `reason: "Sizing violation on speaker <id> beat <idx> cannot be resolved within weight cap and bump budget."`

---

## 5. Do not

- Do not modify `queue.json`.
- Do not touch `recent_chat.json`, `full_chat.json`, or any chat/history file.
- Do not re-spawn the planner yourself — on `status: "restart"`, the orchestrator handles that.
- Do not re-spawn the validator yourself — on `status: "patched"`, the orchestrator re-runs validation.
