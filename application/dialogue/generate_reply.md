# generate_reply — RETIRED

This file has been replaced by a 3-phase pipeline:

1. **`generate_reply_plan.md`** — reads all context, outputs structured plan
2. **`generate_reply_expand.md`** — expands first character's turn into prose (parallel)
3. **`generate_reply_respond.md`** — writes second character's turn as prose (parallel)

See `CLAUDE.md` step 4a for orchestration details.
