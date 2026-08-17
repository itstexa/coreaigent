---
name: senior-developer
description: 'Use when: docs/design/DESIGN.md and docs/architecture/ARCHITECTURE.md both have content EXPLICITLY human-approved in docs/APPROVAL_LOG.md and are ready to be implemented. Third stage of the pipeline, following requirement-analysis and solution-architect. Implements exactly one user story at a time using ATDD (failing acceptance tests from the story''s Gherkin ACs first, then code until green), verifies architecture predicates/invariants are matched, uses the version-control and meaningful-tests skills throughout, writes a per-pass entry to docs/implementation/IMPLEMENTATION_LOG.md (ACs covered, predicates matched, Open Questions, deviations), and never assumes an answer to any ambiguity.'
---

# Senior Developer Skill

Turns approved requirements and architecture into tested, working code — one story at a time, via ATDD, with zero assumptions. This is stage 3 of the pipeline, consuming the output of `requirement-analysis` and `solution-architect`.

## When to Use

- A user story in `docs/design/DESIGN.md` and its corresponding model(s)/decisions in `docs/architecture/ARCHITECTURE.md` are both explicitly approved and ready to build
- Continuing implementation of a partially-built story, or starting the next approved story

## Communication Style Is Independent of This Procedure

This skill defines WHAT to do and WHAT goes in the documents it writes (`IMPLEMENTATION_LOG.md` entries, tables, checklists). It does not define HOW to talk to the human operator. If a compressed communication-style skill (e.g. **caveman**) is active for this session, it governs chat prose for every step of this procedure — Red/Green/Refactor status updates, Open Question call-outs, checklist walkthroughs, approval requests — the same as any other turn, all the way through, not just a closing wrap-up. The only carve-outs are: (1) content written into the actual documents/templates this skill produces, and (2) commit/PR/merge text per **version-control**'s Message Language rule — both stay in the register those artifacts require regardless of chat style.

## Gate: Only Implement What Is Explicitly Approved

Before writing any code for a story:
1. Open `docs/APPROVAL_LOG.md` (the single log shared across the whole pipeline).
2. Confirm there is an entry with **Status: Approved** (Approved By + Approval Date filled in) for **Stage: Requirement Analysis** covering the story in `docs/design/DESIGN.md`.
3. Confirm there is also an entry with **Status: Approved** for **Stage: Solution Architecture** covering the relevant models/decisions in `docs/architecture/ARCHITECTURE.md`.
4. If either is still `Pending Approval`, `Rejected`, or missing — **stop**. Tell the human operator what's blocking implementation. Do not implement against unapproved requirements or architecture, even partially.

## One Story at a Time

Never implement multiple stories in the same pass. Finish (or explicitly pause with a logged status) one story's ATDD cycle before starting the next. This keeps each `IMPLEMENTATION_LOG.md` pass, each branch, and each PR traceable to a single story.

## The One Hard Rule: Never Assume

Same discipline as the earlier stages:
- If the approved DESIGN/ARCHITECTURE docs don't cover a detail needed to write the code (an edge case, a value, a behavior), do not guess or pick the "reasonable" implementation.
- Raise it as an **Open Question** (`IQ-` prefix, see step 6) and stop **only the specific scenario/detail** it blocks — continue implementing the rest of the story's ACs and code that don't depend on the answer. Don't stall the whole story for one unresolved question unless everything left genuinely depends on it.
- If the human operator resolves it in chat, record the exact answer, implement it, and log it as a **Deviation** (step 6) from what the approved docs said — the docs are the source of truth until a human changes them.
- Only proceed with an implementation detail once it's either already specified in the approved docs, or resolved live and logged as a deviation.

## Procedure (ATDD, per story)

### 1. Select and branch
Pick the next approved, not-yet-implemented story. Use the **version-control** skill to draft and get approval for a branch (e.g. `feature/<story-slug>`) before creating it.

### 2. Red — write failing acceptance tests first
From the story's Gherkin ACs in `DESIGN.md`, write acceptance tests for every scenario (happy path and rejection paths) before writing any production code. Apply the **meaningful-tests** skill's discipline while writing them (no vacuous assertions, boundary + epsilon coverage, real negative/zero cases, etc.). Confirm they fail for the right reason (feature doesn't exist yet), not because of a typo/setup bug.

### 3. Green — implement to satisfy the architecture
Write the minimal code to make the acceptance tests pass, while matching what `ARCHITECTURE.md` specifies for the entities/predicates involved:
- Field types/units as specified
- Invariants hold
- Boundary behavior matches (including the limit/limit±epsilon cases)
- Concurrency/race handling matches the documented resolution

Add/extend unit tests as needed, again per the **meaningful-tests** skill.

### 4. Refactor
Clean up while keeping all tests green. Re-run the full acceptance + unit suite after refactoring.

### 5. Commit and open the PR via version-control
Use the **version-control** skill throughout: commit at sensible intervals with structured messages, and open the PR with a structured title/description once the story's ACs are all green — always with human approval before each state-changing git action, executed without delay once approved. Commit/PR/merge text itself is always plain English regardless of any active caveman-style chat (see version-control's Message Language rule) — only the surrounding chat may stay caveman.

### 6. Log Open Questions and deviations
While implementing, if anything is ambiguous, add a row (in the current pass's `IMPLEMENTATION_LOG.md` entry):

| ID | Question | Status | Resolution |
|---|---|---|---|
| IQ-<n> | <the exact ambiguity> | Open | — |

- Mark `Answered` the moment the human operator responds in chat; copy their exact answer into **Resolution**.
- Mark `Resolved` once the code has been updated to reflect it, and add a corresponding row to the pass's **Deviations** list: what changed vs. the approved DESIGN/ARCHITECTURE docs, and which `IQ-`/`OQ-`/`AQ-` resolution caused it.
- Never delete an Open Question or a Deviation — they're part of the traceable history.

### 7. Write the IMPLEMENTATION_LOG.md pass entry
Target file: `docs/implementation/IMPLEMENTATION_LOG.md`, created from [templates/IMPLEMENTATION_LOG.md](./templates/IMPLEMENTATION_LOG.md) if missing. Append one new entry per pass (never edit/delete a previous pass's entry) containing:
- Story, branch, and traces to the exact `DESIGN.md`/`ARCHITECTURE.md` sections
- Acceptance-criteria coverage table (scenario → status → test)
- Predicates/invariants matched table (entity/predicate → invariant → how verified)
- Open Questions raised this pass
- Deviations from the approved docs, with cause
- Version-control actions taken (branch, commits, PR)

### 8. Maintain the shared Approval Log entry
Same convention as the earlier stages, in `docs/APPROVAL_LOG.md`:
- Set **Stage** to `Implementation` for entries this skill creates, listing the story/pass covered.
- Exactly one active entry at a time across the whole pipeline — update in place, don't create a second pending one.
- **Approved By**/**Approval Date** stay blank until a human operator explicitly approves the pass (typically alongside PR review) — never fill these in yourself.

## Completion Checklist
- [ ] Story's requirements and architecture were both confirmed `Approved` in `docs/APPROVAL_LOG.md` before coding started
- [ ] Only one story was implemented in this pass
- [ ] Acceptance tests were written from the Gherkin ACs and observed failing before any production code was written
- [ ] All of the story's AC scenarios (happy path and rejection) pass
- [ ] All touched entities/predicates match their documented types/units, invariants, boundary behavior, and concurrency handling
- [ ] The meaningful-tests skill's 7 failure modes and boundary±epsilon convention were applied to new/changed tests
- [ ] The version-control skill was used for branch/commits/PR, with human approval before each state-changing git action
- [ ] `IMPLEMENTATION_LOG.md` has a new pass entry with AC coverage, predicates matched, Open Questions, and deviations
- [ ] No implementation detail was assumed — every ambiguity became a tracked `IQ-` Open Question
- [ ] `docs/APPROVAL_LOG.md` has an active entry (Stage: Implementation) pending human approval for this pass
