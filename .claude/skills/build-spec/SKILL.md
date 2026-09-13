---
description: orchestrate a spec to done, one builder agent per task and a reviewer agent gating each one
argument-hint: "<slug> [--task N] [--from N] [--solo]"
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent, SendMessage
---

## Context

- Branch: !`git branch --show-current`
- Uncommitted: !`git status --short`
- Recent commits: !`git log --oneline -5`
- Specs on disk: !`ls .claude/specs 2>/dev/null || echo "none"`
- The request: $ARGUMENTS

## Task

You are the orchestrator for `.claude/specs/<slug>/`. You do not write the feature code yourself. You dispatch a
`spec-builder` agent per task, gate each task with a `spec-reviewer` agent, and decide what happens next. If the
slug is missing or ambiguous, list the specs and ask.

With `--solo`, skip the agents and build it yourself under the same rules. Use that only for a one-line task where
dispatching costs more than doing it.

### Before the first dispatch

Read `spec.md` and `tasks.md` in full, plus `CLAUDE.md` and `.claude/skills/open-spec/reference.md`. You have to
know the spec well enough to judge a reviewer's verdict, because the agents see only what you send them.

Then check the ground:

1. **Branch.** You must be on the branch the spec names. On `main`, stop and say so.
2. **Contract.** If the spec's Contract impact is not "None", confirm with the user that the team chat
   announcement went out before any task touches `packages/core`.
3. **Ownership.** If a task edits another lane's package, confirm the owner agreed.
4. **Clean enough tree.** Uncommitted work unrelated to this spec should be committed or set aside first, so each
   task's diff is readable.

### The loop, one task at a time

Tasks are ordered because each builds on the last. Run them serially, from task 1 or from `--from N`, or just the
one named by `--task N`.

For each task:

**1. Dispatch the builder.** One `spec-builder` agent, with a prompt that stands alone. The agent cannot see this
conversation, so give it: the slug and the full path to the spec, the task number and its exact text, the branch,
which spec Behaviour statements the task must satisfy, and anything a previous task decided that this one depends
on, such as a module path or a helper that already exists. Tell it to commit when `make check` is green and to
report without pushing.

**2. Dispatch the reviewer.** When the builder reports, spawn a `spec-reviewer` agent on that commit. Give it the
commit sha, the spec path, the task number, and the builder's own claims. Never let the builder review itself, and
never skip the reviewer because the builder said the check was green: the builder's claim is what you are testing.

**3. Act on the verdict.**

- **pass**: record it, move to the next task.
- **pass with notes**: record the notes, move on. Collect them for the pull request body rather than fixing
  cosmetics mid build.
- **fail**: send the findings back to the same builder with `SendMessage`, so it keeps the context of what it
  wrote. Do not spawn a fresh builder for a fix. Then review again.

Two failed rounds on the same task is a stop. Report to the user what the reviewer wants, what the builder tried,
and your own read of which one is right. Do not start a third round and do not fix it yourself to move things
along.

**4. Keep the ledger.** After each task, append one line to `.claude/specs/<slug>/notes.md`: task number, commit
sha, verdict, and any note. That file is what the pull request body quotes, and what a later session reads if this
one is interrupted.

### Parallel work

Default to serial. Dispatch two builders at once only when the spec makes the independence explicit, for instance
two clients with no shared module, and never when both would touch the same file. A merge conflict between two of
your own agents costs more than the time it saved.

### When the tasks are done

Run `make check` and `make fixture` yourself. Both green. If the spec names an eval row, run `make evals` and read
the new row against the previous SHA. Then hand the whole branch to one final `spec-reviewer` before you tell the
user it is ready.

If the spec turns out to be wrong, stop dispatching. Say which Behaviour statement is wrong, propose the edit in a
sentence, and wait. Never let an agent quietly build something the spec does not say.

## Output

- **Built**: <tasks done out of total>, commits <first sha>..<last sha>
- **Per task**: number, commit, verdict, one line each
- **Tests**: names added, and which reliability tests were watched red
- **check / fixture**: green, or the exact failing output
- **Left**: tasks not done and why, or "none"
- **Contract**: what changed in core and who was told, or "untouched"

End with the next command: `/check-spec <slug>`.
