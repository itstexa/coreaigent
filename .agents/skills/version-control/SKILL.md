---
name: version-control
description: 'Use when: creating a branch, making a commit, merging, pushing, or opening/updating a PR in this repo. Enforces mergeable, traceable git hygiene — consistent branch naming by change type, commits at sensible logical intervals with structured messages, well-structured PR titles/descriptions — and requires explicit human-operator approval before executing any state-changing git action, then executes immediately without delay once approved unless a real concern surfaces as a question.'
---

# Version Control Skill

Keeps this repository's git history mergeable and traceable: consistent branch names, sensibly-scoped commits with clear messages, well-structured PRs — and a hard approval gate before any of it actually touches repo state.

## When to Use

- About to create/rename a branch
- About to stage and commit changes
- About to push, merge, or open/update a pull request
- Reviewing whether now is a good point to make a commit

## Core Rule: Approval Before Action, No Delay After It

This skill's approval gate is **stricter than normal** — it applies to every state-changing git action, not just destructive ones:

1. Before running any command that changes repo state (`git branch`/`checkout -b`, `git add`/`commit`, `git push`, `git merge`, opening/updating a PR), stop and present the human operator with the **exact** draft: branch name, or full commit message, or PR title + body.
2. For a multi-step piece of work, it's fine to present the **whole planned sequence of commits** (each with its intended message and rough diff scope) in one go for a single batch approval, rather than stopping after every individual commit.
3. Wait for explicit approval. Do not execute speculatively "to save a round trip."
4. Once approved, execute the approved action(s) immediately, in order — don't re-ask per commit once the batch is approved.
5. If something changes mid-sequence, or a real concern surfaces (merge conflicts, failing tests/build, unstaged files that don't belong, diverged branch, a later commit no longer matches what was approved), **stop and surface it as a question** instead of proceeding or silently resolving it.

## Message Language — Always Plain English

Commit messages, PR titles/descriptions, and merge commit messages are always written in plain, normal English — never caveman-compressed or otherwise abbreviated — regardless of any active communication-style skill (e.g. **caveman**) and regardless of how the surrounding chat is being phrased. These become permanent shared project history read by reviewers and future maintainers, not ephemeral chat. This applies even if the caveman skill's own content isn't loaded in context this turn — treat it as a standing rule of this skill, not something that depends on cross-referencing caveman.

## Branch Naming

Scheme: `<type>/<short-kebab-description>`. Keep names purely descriptive — do not append ticket/issue ids.

| Type | Use for |
|---|---|
| `feature/` | New functionality |
| `bugfix/` | Non-urgent bug fix |
| `hotfix/` | Urgent production fix |
| `chore/` | Tooling, deps, config, no behavior change |
| `refactor/` | Restructuring without behavior change |
| `docs/` | Documentation only |
| `test/` | Test-only changes |
| `release/` | Release preparation |

Examples: `feature/password-reset`, `bugfix/checkout-null-pointer`, `chore/update-dependencies`.

## Commit Cadence

Commit at **sensible logical intervals** — neither line-by-line nor one giant end-of-task dump. A commit is due when:
- A coherent unit of work reaches a working state (builds/tests pass)
- You're about to switch to a different concern/file area
- You're about to attempt something risky (refactor, dependency bump), so there's a safe rollback point

Each commit should represent one coherent, logically-scoped change — don't bundle unrelated changes into one commit, and don't split one logical change across many.

## Commit Message Structure

```
<type>(<scope>): <concise imperative summary, ~50 chars>

<body: what changed and why — wrap ~72 chars, bullets OK>

<footer: refs #issue, breaking changes, etc. — optional>
```

`type` ∈ `feat, fix, docs, style, refactor, test, chore, perf, ci, build` (mirrors the branch type it belongs to — e.g. work on a `feature/` branch normally produces `feat` commits, `bugfix/` produces `fix` commits).

## PR Title & Description Structure

Title: same convention as a commit summary line — `<type>(<scope>): <concise summary>`.

Description template:

```
## Summary
<what changed, one or two sentences>

## Why
<motivation — link the driving issue/request, and any docs/design or docs/architecture entries if relevant>

## Changes
- <notable change 1>
- <notable change 2>

## Testing
<how this was verified>
```

### Merging
Default merge strategy for approved PRs is **squash merge**, producing one clean commit on the target branch using the PR title/summary as the squashed commit message. Only deviate (merge commit / rebase) if the human operator explicitly asks for it.

## Procedure

1. Inspect current git state before proposing anything: `git status`, `git branch --show-current`, `git log --oneline -n 10`.
2. Decide what action is warranted (new branch? commit checkpoint? push? open/update PR? merge?) based on Branch Naming / Commit Cadence above.
3. Draft the exact action — branch name, or full commit message, or PR title+body — following the structures above. For multi-commit work, draft the full planned sequence.
4. Present the draft(s) to the human operator and ask for approval. Never run the state-changing command first and ask after.
5. On approval, execute immediately via the terminal (or appropriate tool), working through an approved batch in order without re-asking per step.
6. On a requested change, revise the draft and re-present — don't partially execute the old draft.
7. If execution surfaces a real concern (conflicts, failing checks, unexpected diff, diverged remote, a step that no longer matches what was approved), stop and ask rather than guessing a resolution or forcing it through.

## Completion Checklist

- [ ] Branch name follows `<type>/<description>` and matches the nature of the work
- [ ] Each commit is one coherent, sensibly-scoped unit of work
- [ ] Commit message follows `type(scope): summary` + body structure
- [ ] PR title/description follow the template and link related context
- [ ] Explicit human approval was obtained before any state-changing git action
- [ ] Approved actions were executed without unnecessary delay
- [ ] Any real concerns encountered were surfaced as questions, not silently resolved
