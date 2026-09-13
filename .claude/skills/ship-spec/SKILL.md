---
description: merge main, prove the check is green, push the branch and open the PR that closes the issue
argument-hint: "[slug] [--go] [--draft]"
allowed-tools: Bash, Read, Write, Grep, Glob
---

## Context

- Branch: !`git branch --show-current`
- Uncommitted: !`git status --short`
- Commits to ship: !`git log --oneline origin/main..HEAD 2>/dev/null | head -20`
- Open PR for this branch: !`gh pr view --json number,state,title 2>/dev/null || echo "none"`
- Specs on disk: !`ls .claude/specs 2>/dev/null || echo "none"`
- The request: $ARGUMENTS

## Task

Open the pull request for `.claude/specs/<slug>/`. With no slug, infer it from the branch name and say which
spec you used. Read that spec, `CLAUDE.md` and `.claude/skills/open-spec/reference.md` first.

Pushing and opening a PR are outward facing. Print the plan, then stop and ask, unless `--go` is in the
arguments.

### 1. Preflight, in this order

Any failure stops the ship. Report it and do not push.

1. Not on `main`. Never push `main`, never force push it.
2. Working tree clean. Uncommitted work either belongs in a commit or does not belong on this branch.
3. Every box in `tasks.md` ticked, or the user has said which ones ship later.
4. Main merged in, because a PR with conflicts gets no PR run:
   ```sh
   git fetch origin && git merge origin/main
   ```
   Conflicts are yours to resolve before anything else, and `make check` runs again after.
5. `make check` green on the merge result.
6. `make fixture` green. Rule 10: nothing merges that breaks the fixture run.
7. `git diff origin/main...HEAD` contains no key, token or credential, and no em dash in user visible copy.
   Grep for it, do not trust a read.

### 2. Push and open

```sh
git push -u origin <branch>
gh pr create --title "<lane letter>: <what it does>" --body-file <body>
```

`--force-with-lease` only, and only on your own branch. Never amend a commit that is already pushed.
Use `--draft` only when the user asks: rule 4 wants the PR non draft the moment `make check` passes.

The PR body:

```markdown
## What
<one sentence, the same goal sentence as the spec>

## Why
<the eval row or the demo moment this feeds>

## Contract
<none, or the additive change and the chat announcement that went out>

## Proof
- `make check` green at <sha>
- `make fixture` green at <sha>
- tests: <names, and the reliability test that plants the failure>
- evals: <row before and after, or "not run">

## Reviewer notes
<what to look at first, and anything deliberately left out>

Closes #<issue>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

Take the issue number from the spec. If the spec has none, find it with `gh issue list` or say the PR closes
nothing and let the user decide.

### 3. Watch CI

CI must be green on the head SHA, not on an older one.

```sh
gh pr checks --watch
```

If it goes red, report the failing job and the first error line, fix it on the branch, and push again. Do not
merge. Rule 4: anyone but the author merges on green, and Lane A breaks ties.

### 4. Tell the team

Print the chat message for the user to post, in the template from `CLAUDE.md`:

```
<lane>: LIVE — <what works on main, the command to try it>
```

and, when the contract changed:

```
<lane>: CONTRACT — <what changed, what to pull>
```

## Output

Report in this form:

- **PR**: <url>, or the commands waiting for a yes
- **Preflight**: each of the seven, pass or the failure
- **CI**: green on <sha>, red with <job and first error>, or still running
- **Closes**: #<issue>, or "no issue"
- **Post this**: the chat line, ready to copy

Do not merge the PR yourself. Say who can.
