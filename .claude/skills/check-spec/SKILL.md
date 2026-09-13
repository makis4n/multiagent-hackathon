---
description: test and review a feature against its spec and the repo rules before it becomes a PR
argument-hint: "[slug] [--fix] [--evals]"
allowed-tools: Bash, Read, Grep, Glob, Write, Agent
---

## Context

- Branch: !`git branch --show-current`
- Uncommitted: !`git status --short`
- Commits on this branch: !`git log --oneline origin/main..HEAD 2>/dev/null | head -20`
- Files changed against main: !`git diff --stat origin/main...HEAD 2>/dev/null | tail -30`
- Specs on disk: !`ls .claude/specs 2>/dev/null || echo "none"`
- The request: $ARGUMENTS

## Task

Decide whether this branch is ready to be a PR. You are the reviewer, not the author: look for what is wrong,
and prove each finding from the diff or from a command you ran. Read the spec at `.claude/specs/<slug>/spec.md`,
then `CLAUDE.md` and `.claude/skills/open-spec/reference.md`. With no slug, infer it from the branch name and say which
spec you used.

### 1. Run it

In this order, and quote the real output:

```sh
make check
make fixture
uv run pytest <the package you changed> -q
```

Add `make evals` when `--evals` is given or the spec names an eval row. Compare the new row against
`evals/results/` for the previous SHA and say which way it moved.

A red check ends the review. Report the failure and stop.

### 2. Read the diff

`git diff origin/main...HEAD`. Read every hunk. Check each item and mark it pass, fail or not applicable:

| # | Check |
| --- | --- |
| spec | every Behaviour statement in the spec has code, and every test in the spec exists and runs |
| 1 | `packages/core` changes are additive only, and every fake and implementer moved with them |
| 2 | nothing edited outside the lane's package without the owner's answer |
| 5 | every tool is callable without a model; every Protocol touched has a fake; tests are offline with `respx` |
| 6 | every reliability claim has a test that plants the failure, not prose |
| 7 | no order without `confirmed_by_user_at`; the idempotency key is looked up before creating; the Duffel client refuses a key that is not `duffel_test_` |
| 8 | no key, token or credential in code, tests, fixtures, logs or a scratch file; new keys declared empty in `.env.example` |
| 12 | one `CallLog` line per tool call, no raw bodies, the stack not the message, every response status checked, no bare `except` |
| 13 | user visible copy says what happens, and has no em dashes |
| llm | model calls go through `complete_json` with a flat schema, no dicts |
| patch | the itinerary changes only through `ItineraryPatch`, never a regeneration |
| size | the diff is one feature. If it is two, say which to split out |

Run the cheap greps rather than trusting a read: search the diff for `except:`, for `—`, for `api_key`,
`secret`, `token` assignments, and for `requests.` or `httpx.` calls inside tests.

### Delegating the read

For a branch with more than about five commits, spawn a `spec-reviewer` agent per area rather than reading
everything yourself: one on the diff, one on the tests, one on the rule checklist. Give each the spec path and
its slice, then reconcile the verdicts. You still run the commands yourself, and you still own the final verdict:
an agent's finding without a `file:line` and a rule number does not make it into your report.

### 3. Judge

Rank findings by severity. A finding is blocking if it breaks a rule in `CLAUDE.md`, breaks `make fixture`,
leaks a secret, or means the spec is not met. Everything else is a note.

With `--fix`, fix only the blocking findings, one commit each, and rerun `make check`. Without it, change
nothing: report and stop.

Append what you found to `.claude/specs/<slug>/notes.md` with the date and the head SHA, so the PR body can
quote it.

## Output

Report in this form:

- **Verdict**: ready for PR, or blocked
- **check / fixture / tests**: green or the failing output, one line each
- **Evals**: <row, before and after>, or "not run"
- **Blocking**: numbered, each with `file:line`, what breaks, and the rule number
- **Notes**: numbered, same shape, non blocking
- **Spec coverage**: <behaviour statements covered> of <total>, and which are missing

End with the next command: `/ship-spec <slug>` when the verdict is ready.
