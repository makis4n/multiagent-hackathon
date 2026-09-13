---
description: turn a feature idea into a lane-scoped spec, task list, issue and branch
argument-hint: "<feature in one line> [--lane B|C|D|A] [--go]"
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

## Context

- Branch: !`git branch --show-current`
- Uncommitted: !`git status --short`
- Recent commits: !`git log --oneline -5`
- Package owners: !`for f in packages/*/README.md apps/agent/README.md; do echo "$f: $(sed -n '1,6p' "$f" | rg -i 'owner|status' | head -1)"; done`
- Existing specs: !`ls .claude/specs 2>/dev/null || echo "none"`
- The feature: $ARGUMENTS

## Task

Turn the feature request into a spec that another agent, or another human, can build from without asking a
question. Read `CLAUDE.md`, `ARCHITECTURE.md` and `.claude/skills/open-spec/reference.md` first. Read the code you are
about to change: the Protocol in `packages/core/trip_core/tools.py`, its fake in `trip_core/fakes.py`, and the
package you will write in. Do not guess at a signature you have not read.

### 1. Place the feature

Name the lane and the package from the owner lines above, not from the table in the reference. If the feature
lands in a package someone else owns, say so and stop: the owner answers in the team chat first.

If `--lane` is given, use it, and say so if the code suggests a different one.

### 2. Decide the contract impact

Three cases, in order of preference:

- **None.** The feature is a real implementation behind an existing Protocol and an existing flag. Best case.
- **Additive.** A new model, a new field with a default, or a new Protocol member. Spell out every fake and every
  implementer that must ship in the same PR. The spec says the team chat announcement must go out before any
  edit to `packages/core`, and the skill does not make that edit until the user confirms the message was sent.
- **A rename or a removal.** Not yours to decide. Write it as a question for Lane A and stop.

### 3. Write the spec

Choose a slug: short, kebab case, the thing not the lane, for example `reddit-signals` or `transit-reachable`.
Write `.claude/specs/<slug>/spec.md`:

```markdown
# <feature title>

Lane <letter>, `packages/<pkg>`. Branch `lane/<letter>-<topic>`. Flag `REAL_<LANE>`.

## Goal
<one sentence: what the user or the eval table can do after this that it cannot do now>

## Contract impact
<none, or the exact additive change plus every fake and implementer that ships with it>

## Behaviour
<numbered, testable statements over contract types. Inputs, outputs, and what happens on each failure.
One line each. Name the Protocol member each statement belongs to.>

## Failure handling
<per external call: what fails, how it is detected, what the code does. Transport and rate limit failures
surface as RetryableError. No bare except. Every response checks its status.>

## Tests that prove it
<one line per test: file, name, what it plants and what it asserts. Recorded with respx, offline.
Every reliability claim in Behaviour has a test here that goes red against the current code.>

## Out of scope
<what this feature deliberately does not do, so the PR stays small>

## Done when
- `make check` green
- `make fixture` green
- <the eval row this moves, or "no eval row">
- <the demo moment this feeds, or "none">
```

Keep Behaviour under about ten statements. If it needs more, it is two features: write the second spec and say
which one to build first.

### 4. Write the task list

Write `.claude/specs/<slug>/tasks.md` as an ordered checklist of commits, not of files. Each line is one logical
step that leaves `make check` green. Tests come with the code that makes them pass, in the same step. First step
is usually the fake or the recorded cassette; last step is usually wiring the flag in `apps/agent/trip_agent/registry.py`,
which is Lane A's file and needs a message in the team chat if you do not own it.

```markdown
# Tasks: <slug>

- [ ] 1. <commit message: what changes, what test covers it>
- [ ] 2. ...
```

### 5. Open the issue and the branch

Print the plan first: the issue title, the issue body, the branch name. Then stop and ask, unless `--go` is in
the arguments. On confirmation, or with `--go`:

```sh
git fetch origin && git checkout main && git pull --rebase origin main
git checkout -b lane/<letter>-<topic>
gh issue create --title "<lane letter>: <title>" --body "<goal, behaviour summary, done when>"
```

Write the issue number into the spec under the title as `Issue #<n>`. Do not create the issue while the working
tree has uncommitted changes that belong to another piece of work: say so and let the user clear them.

## Output

Report in this form:

- **Feature**: <title>, lane <letter>, `packages/<pkg>`
- **Contract**: none, or the additive change and who must be told
- **Spec**: `.claude/specs/<slug>/spec.md`, <n> behaviour statements, <n> tests
- **Branch and issue**: created, or the exact commands waiting for a yes
- **Risks**: <what could make this the wrong shape, or "none">

End with the next command: `/build-spec <slug>`.
