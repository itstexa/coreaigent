# Approval Log

> Single file shared by the **entire pipeline** (`requirement-analysis`, `solution-architect`, and any future stage). Exactly **one active entry** exists at a time. Agents update it as an audit record; they do not wait for manual Markdown edits. A human records approval with `python3 .agents/tools/approval.py approve --stage "<Stage>" --by "<name>"`.

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
