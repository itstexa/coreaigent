---
name: requirement-analysis
description: 'Use when: a new feature, change, or scope is requested in chat by a human operator and no acceptance criteria exist yet. Converts free-text requests into user stories and testable Gherkin acceptance criteria (with explicit rejection/negative paths), writes them to docs/design/DESIGN.md, splits overflow into linked design session files, tracks every ambiguity as an Open Question (never assumes), and records stage approval in docs/APPROVAL_LOG.md through the repository approval CLI.'
---

# Requirement Analysis Skill

Turns a human operator's free-text feature/change request into structured, testable requirements — without ever guessing at intent.

## When to Use

- A new feature, change, or scope has been requested directly by a human operator in chat
- The request has no user stories or acceptance criteria (ACs) defined yet
- An existing story/AC needs to be extended and the same no-assumptions discipline applies

## The One Hard Rule: Never Assume

If any part of the request is ambiguous, underspecified, or could reasonably resolve in more than one way:
- Do **not** guess and write an AC around the guess.
- Do **not** silently pick the "most likely" interpretation.
- Write it down as an **Open Question** instead (see step 4) and stub the story/AC as blocked on it.
- Only write the final AC once the human operator resolves the question — either directly in chat, or by editing the Open Question's row in the DESIGN file.

Approval is a stage transition, not an interactive wait state. Finish all
unblocked analysis, record the pending entry, and report the approval command.
Do not poll, pause for a manual edit, or fill in approval fields yourself.

## Procedure

### 1. Locate or initialize the design doc
- Target file: `docs/design/DESIGN.md`.
- If it doesn't exist, create it from [templates/DESIGN.md](./templates/DESIGN.md).
- If it exists, read it fully before editing — do not blindly append.

### 2. Check whether to split into a session file
`DESIGN.md` acts as an **atlas** (a central index). Split when the file is becoming unwieldy to review in one sitting — as a rule of thumb, when it exceeds roughly **400 lines** or the current session is about to add a substantial new chunk of stories/ACs to an already-large file.

To split:
1. Get the last-seen commit id before this session's edits: `git rev-parse --short HEAD`.
2. Create `docs/design/DESIGN_<commit-id>.md` from [templates/DESIGN_SESSION.md](./templates/DESIGN_SESSION.md).
3. Add a row for it in the **Linked Design Documents** table at the top of `DESIGN.md` (the atlas entry), so `DESIGN.md` always shows every session file that exists.
4. Write this session's new stories/ACs/Open Questions into the session file, not into `DESIGN.md` directly.
5. Once a commit/PR is opened for the work, the session file becomes a **permanent linked record** — never fold it back into `DESIGN.md`. Its atlas row simply changes from `Active` to `Merged`/`Closed`.

### 3. Write user stories
For each distinct piece of scope, write a story:

```
### US-<n>: <short title>
As a <role>
I want <capability>
So that <benefit>
```

### 4. Write Gherkin acceptance criteria — with rejection paths
For each story, write one `Feature`/`Scenario` block per behavior. Every story must include:
- At least one **positive** (happy path) scenario
- At least one **negative/rejection** scenario (invalid input, unauthorized action, precondition not met, etc.)

```
Feature: <story title>

  Scenario: <happy path>
    Given <context>
    When <action>
    Then <expected outcome>

  Scenario: <rejection path>
    Given <context>
    When <invalid/unauthorized action>
    Then <system rejects / error is shown / state unchanged>
```

If a scenario can't be written without assuming an unresolved detail, don't write it — raise an Open Question instead (step 5).

### 5. Log Open Questions instead of assuming
Add a row to the Open Questions table (in `DESIGN.md` or the active session file):

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| OQ-<n> | <the exact ambiguity> | requirement-analysis | Open | — |

- **Status** progresses `Open → Answered → Resolved`.
- Mark `Answered` the moment the human operator responds in chat; copy their exact answer into **Resolution**.
- Mark `Resolved` once the corresponding story/AC has been written or updated to reflect that answer.
- Never delete an Open Question — history of decisions matters.

### 6. Maintain the single, shared Approval Log entry
Target file: `docs/APPROVAL_LOG.md` — **one file shared by the entire pipeline** (requirement-analysis, solution-architect, and any future stage), created from [templates/APPROVAL_LOG.md](./templates/APPROVAL_LOG.md) if missing.

Rules (this mechanism is shared by other skills too, not just this one):
- There is exactly **one active entry** at a time across the whole pipeline (status `Pending Approval`). Update it in place as work progresses — do not create a second pending entry, even if another skill's stage is active.
- Set **Stage** to `Requirement Analysis` for entries this skill creates.
- Append new decisions/scope covered/resolved Open Questions to the active entry's lists as the session continues.
- The active entry must contain: Status, Stage, Session Started date, Related Doc(s), Requested By, Decisions/Scope Covered, Open Questions Resolved, Approved By, Approval Date.
- Leave **Approved By** / **Approval Date** blank. The human operator records approval with:
  `python3 .agents/tools/approval.py approve --stage "Requirement Analysis" --by "<name>"`.
- After the command succeeds, a later pipeline invocation may consume the `Approved` entry. Do not wait in the current invocation for the command or ask the operator to edit Markdown by hand.
- The log is an audit record. Moving an entry to **History** is bookkeeping after the associated work lands, not a reason to block analysis.

## Completion Checklist
- [ ] Every story has at least one positive and one negative Gherkin scenario, or is explicitly blocked on an Open Question
- [ ] No AC was written by assuming an answer to something ambiguous
- [ ] Every ambiguity has a corresponding Open Question row with correct status
- [ ] `DESIGN.md`'s atlas table lists every session file that currently exists
- [ ] `docs/APPROVAL_LOG.md` has exactly one active entry (Stage: Requirement Analysis); pending approval is recorded, not waited on
