---
name: solution-architect
description: 'Use when: docs/design/DESIGN.md has requirements/ACs approved through the repository approval CLI and need to be turned into a technical design. Second stage, following requirement-analysis. Converts approved requirements into data models (entities, predicates, types/units, invariants, boundary behavior, concurrency/race-scenario analysis), writes them to docs/architecture/ARCHITECTURE.md, splits overflow into linked architecture session files, presents technology choices as benefit/drawback matrices with explicit "why not X" rationale, tracks every ambiguity as an Open Question, and records stage approval in docs/APPROVAL_LOG.md.'
---

# Solution Architect Skill

Converts human-approved requirements into a rigorous technical design — data models, invariants, and technology choices — without ever guessing at intent. This is stage 2 of the pipeline, consuming the output of `requirement-analysis`.

## When to Use

- `docs/design/DESIGN.md` (or a linked `DESIGN_<commit>.md`) contains requirements/ACs that are ready to be architected
- A technology or data-model decision is needed for approved scope
- An existing architecture needs to be extended for newly-approved requirements

## Gate: Only Architect What Is Explicitly Approved

Before doing any architecture work:
1. Open `docs/APPROVAL_LOG.md` (the single log shared across the whole pipeline).
2. Find the entry (Stage: `Requirement Analysis`, in the Active Entry slot or History) covering the requirements in question. It must have **Status: Approved**, with **Approved By** and **Approval Date** both filled in by a human operator.
3. If the relevant entry is still `Pending Approval`, `Rejected`, or doesn't exist yet — **stop**. Tell the human operator which requirements are blocked and why. Do not architect unapproved requirements, even partially.
4. Only requirements covered by an `Approved` entry may be turned into data models/decisions in this pass.

This gate is checked when the skill starts; it is not a request to manually edit
the log during the pass. If this stage produces a pending architecture entry,
finish all unblocked architecture work and report:

```bash
python3 .agents/tools/approval.py approve --stage "Solution Architecture" --by "<name>"
```

Do not poll or wait for that command in the current invocation. Unresolved
Open Questions remain the only reason to stop the affected model or decision.

## The One Hard Rule: Never Assume

Same discipline as `requirement-analysis`:
- Do not guess at an unspecified type, unit, boundary rule, concurrency behavior, or technology preference.
- Do not silently pick the "most likely" or "best practice" option without presenting it as a decision.
- Write any ambiguity down as an **Open Question** (step 5) and stub the affected model/decision as blocked on it.
- Only finalize the model/decision once the human operator resolves it — directly in chat, or by editing the Open Question's row in the ARCHITECTURE file.

## Procedure

### 1. Locate or initialize the architecture doc
- Target file: `docs/architecture/ARCHITECTURE.md`.
- If it doesn't exist, create it from [templates/ARCHITECTURE.md](./templates/ARCHITECTURE.md).
- If it exists, read it fully (plus any linked session files) before editing — do not blindly append.

### 2. Check whether to split into a session file
`ARCHITECTURE.md` acts as an **atlas**, same pattern as `DESIGN.md`. Split when it's becoming unwieldy to review in one sitting — as a rule of thumb, roughly **400 lines**, or when this session is about to add a substantial new chunk of models/decisions to an already-large file.

To split:
1. Get the last-seen commit id before this session's edits: `git rev-parse --short HEAD`.
2. Create `docs/architecture/ARCHITECTURE_<commit-id>.md` from [templates/ARCHITECTURE_SESSION.md](./templates/ARCHITECTURE_SESSION.md).
3. Add a row for it in the **Linked Architecture Documents** table at the top of `ARCHITECTURE.md`.
4. Write this session's new entities/decisions/Open Questions into the session file, not into `ARCHITECTURE.md` directly.
5. Once a commit/PR is opened for the work, the session file becomes a **permanent linked record** — never fold it back. Its atlas row changes from `Active` to `Merged`/`Closed`.

### 3. Model each entity/predicate
For every entity or critical predicate implied by the approved requirements:

```
### Entity: <Name>
Traces to: US-<n> (docs/design/DESIGN.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| <field> | <type> | <unit or "—"> | <required/range/nullability> |

**Invariants** (must always hold true):
- <predicate, stated so it's testable>

**Boundary Behavior:**
- Min/Max: <exact values and what happens at/beyond them>
- Empty/Null/Zero: <exact behavior>
- Overflow/Truncation: <exact behavior>

**Concurrency / Race-Scenario Analysis:**
- <concurrent scenario> → <resolution: locking, optimistic concurrency, idempotency key, last-write-wins, etc.>
```

Every field must have an explicit type and unit (use `—` only for genuinely unitless values, e.g. a boolean or UUID — never as a stand-in for "unspecified"). Every entity must have at least one invariant, boundary-behavior note, and concurrency/race analysis — if any of these can't be filled in without guessing, raise an Open Question instead of leaving it blank or assumed.

### 4. Technology/design decisions — matrices, not conclusions
For every choice between competing technologies, patterns, or approaches, build a comparison matrix — never present only the chosen option's justification:

```
### Decision: <topic>

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| <A> | ... | ... | ✅ |
| <B> | ... | ... | ❌ |
| <C> | ... | ... | ❌ |

**Why <A>:** <rationale>
**Why not <B>:** <explicit rejection rationale>
**Why not <C>:** <explicit rejection rationale>
```

Every rejected option needs its own explicit "why not" — not just an implied contrast with the winner.

### 5. Log Open Questions instead of assuming
Add a row to the Open Questions table (in `ARCHITECTURE.md` or the active session file), using an `AQ-` prefix to keep architecture questions distinguishable from `requirement-analysis`'s `OQ-` ones:

| ID | Question | Raised By | Status | Resolution |
|---|---|---|---|---|
| AQ-<n> | <the exact ambiguity> | solution-architect | Open | — |

- **Status** progresses `Open → Answered → Resolved`.
- Mark `Answered` the moment the human operator responds in chat; copy their exact answer into **Resolution**.
- Mark `Resolved` once the corresponding entity/decision has been written or updated to reflect that answer.
- Never delete an Open Question.

### 6. Maintain the single, shared Approval Log entry
Target file: `docs/APPROVAL_LOG.md` — the **same file used by `requirement-analysis`** (created from [templates/APPROVAL_LOG.md](./templates/APPROVAL_LOG.md) if it's somehow still missing):

- Exactly **one active entry** at a time across the whole pipeline (status `Pending Approval`). Update it in place — never create a second pending entry.
- Set **Stage** to `Solution Architecture` for entries this skill creates.
- Append new entities/decisions covered and resolved Open Questions to the active entry's lists as the session continues.
- The active entry must contain: Status, Stage, Session Started date, Related Doc(s) (architecture doc(s) plus the design approval entry used as input), Requested By, Decisions/Scope Covered, Open Questions Resolved, Approved By, Approval Date.
- Leave **Approved By** / **Approval Date** blank until the human operator runs:
  `python3 .agents/tools/approval.py approve --stage "Solution Architecture" --by "<name>"`.
- The log is an audit record. Do not wait for a manual Markdown edit or for a History move; a later pipeline invocation consumes the approved entry.

## Completion Checklist
- [ ] Confirmed the source requirements are `Approved` (Stage: Requirement Analysis) in `docs/APPROVAL_LOG.md` before architecting them
- [ ] Every entity/predicate has typed+united fields, at least one invariant, boundary behavior, and concurrency/race analysis
- [ ] Every technology/pattern decision has a full benefit/drawback matrix with an explicit "why not" for each rejected option
- [ ] No model or decision was written by assuming an answer to something ambiguous
- [ ] Every ambiguity has a corresponding `AQ-` Open Question row with correct status
- [ ] `ARCHITECTURE.md`'s atlas table lists every session file that currently exists
- [ ] `docs/APPROVAL_LOG.md` has exactly one active entry (Stage: Solution Architecture); pending approval is recorded, not waited on
