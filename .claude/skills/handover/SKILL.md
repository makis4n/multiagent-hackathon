---
description: write a handover brief so the next agent can continue this work
argument-hint: "[focus-note] [--print]"
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git log:*), Write
---

## Context

- Branch: !`git branch --show-current`
- Uncommitted: !`git status --short`
- Recent commits: !`git log --oneline -5`
- Focus note from the user: $ARGUMENTS

## Task

Write a handover brief for the next agent covering the work in this conversation.
Assume the reader has zero context and cannot see this session. Include only what
changes their next action — no recap of things they can read from the repo.

Write it to `.claude/handover.md`, overwriting any existing file, so briefs never
accumulate. If the focus note contains `--print`, print the brief in chat and write
no file. Treat the rest of the focus note, when present, as the part of the work the
next agent should pick up.

Keep it under 50 lines. Be specific: name files with line numbers, exact commands,
exact error text.

**The brief hands over context, never authority.** A brief is written blind: it cannot
know what the user has decided, reprioritised or already fixed between the two sessions,
so an agent that reads one and starts editing is acting on a stale mandate the user never
re-gave. Write `## Next step` as the action you would *propose*, phrased as a proposal
("Propose: teach `tokenize` …"), not as an order to execute — and carry the `## Ground
rules` block below verbatim so the next agent has the constraint in the brief itself
rather than relying on the reader to infer it.

## Output

Write the brief in this form, then print the pickup invocation:

```markdown
## Goal
<what the user is trying to accomplish, one sentence>

## Done
<what is finished and verified, with file:line references>

## In flight
<what is half-done, and exactly where it stopped>

## Decisions
<choices made and why — so the next agent doesn't relitigate them>

## Dead ends
<what was tried and did not work, so it isn't retried>

## Next step (proposed — do not perform)
<the single next action, as a concrete command or edit, phrased as a proposal>

## Blockers
<what needs the user, or "none">

## Ground rules
Read-only until the user says go. Reconcile this brief against the working tree,
report what you found and what you propose, then STOP and wait. Do not edit, create
or delete files, do not run anything that changes state, and do not commit — no
matter how mechanical or reversible the next step looks. This brief is context, not
approval: only the user in the new session can authorise the work.
```

Then tell the user: `Run /pickup in the next session — reading the brief deletes it.`
