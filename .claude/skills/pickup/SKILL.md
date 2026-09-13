---
description: read the handover brief from the previous agent and delete it
allowed-tools: Bash(cat:*), Bash(rm:*), Bash(git status:*)
---

## Context

- Handover brief: !`cat .claude/handover.md 2>/dev/null && rm -f .claude/handover.md || echo "NO_HANDOVER"`
- Working tree: !`git status --short`

## Task

Absorb the handover brief above as your starting context. It is already deleted from
disk — the `cat` and `rm` ran in the same shell, so this brief exists only in this
conversation now. Do not write it back to a file.

If the brief is `NO_HANDOVER`, tell the user no brief was found and stop; do not
guess at prior context.

Otherwise reconcile the brief against the working tree: if `Done` items are missing
from the tree, or the tree has changes the brief doesn't mention, say so rather than
trusting the brief.

**Then stop.** Reconciling is read-only, and so is this whole command. Do not edit,
create or delete files, do not run anything that changes state, and do not commit —
however mechanical the `Next step` looks. The brief was written by an agent that could
not know what the user decided in between, so it carries context, not approval. The
user re-authorises the work in this session, in their own words, before anything is
touched.

## Output

Report in this form, then wait for the user's go-ahead:
- **Goal**: <one sentence from the brief>
- **Proposed next step**: <the brief's next step, as a proposal>
- **Drift**: <mismatches with the working tree, or "none">
- **Blocked on**: <what needs the user, or "none">

End with the one question that unblocks you — usually "shall I proceed with the
proposed next step?", or the `Blockers` question when there is one.
