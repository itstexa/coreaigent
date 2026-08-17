# Approval Log

> Single file shared by the **entire pipeline** (`requirement-analysis`, `solution-architect`, and any future stage). Exactly **one active entry** exists at a time, regardless of which stage/skill created it, with status `Pending Approval`. Update it in place as decisions accumulate during a session — never create a second pending entry. Once a human operator explicitly sets it to `Approved` or `Rejected` and the associated commit/PR lands, move it to History below and leave the active slot empty for the next stage to use.

## Active Entry

- **Status**: Pending Approval
- **Stage**: <!-- e.g. Requirement Analysis | Solution Architecture -->
- **Session Started**: <date>
- **Related Doc(s)**: <!-- e.g. docs/design/DESIGN.md, docs/architecture/ARCHITECTURE.md -->
- **Requested By**: <human operator>
- **Decisions / Scope Covered**:
  - <decision 1>
- **Open Questions Resolved This Session**:
  - <ID — short resolution summary>
- **Approved By**: <!-- leave blank until a human operator approves -->
- **Approval Date**: <!-- leave blank until approved -->

---

## History

<!-- Move closed (Approved/Rejected) entries here, most recent first, once their commit/PR has landed. Keep the Stage field so it's clear which pipeline phase each entry belonged to. -->
