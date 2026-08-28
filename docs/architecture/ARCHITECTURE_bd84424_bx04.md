# Architecture Session — BX-04 abuse and aggression signals

> Consumes the approved BX-04 requirements in
> `docs/design/DESIGN_bd84424_extensions.md`.

## Boundary and ownership

`workflow` owns the case-scoped abuse assessment because it already owns the
case projection and BX-00 action log. The feature adds no service, database,
CAPTCHA provider, ban list, or mandatory model dependency. Analysis runs after
intake text is normalized and is a deterministic review signal; it never
rejects or stops ordinary case processing.

The optional model is an adapter boundary only. Its short result is validated
before use and its raw inference is not persisted. Config owns term lists,
signal weights, and the `0.70` flag threshold.

## Data model

`case_abuse_assessments` stores one current projection per case:

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `case_id` | UUID | — | Required; primary key and current case foreign key. |
| `label` | enum string | — | `clear` or `flagged`; derived from score and threshold unless overridden. |
| `risk_score` | decimal | unitless `[0,1]` | Required; exact bounds inclusive. |
| `signals` | JSON array of enum strings | — | Only configured signal names; empty is valid for a clear result. |
| `override_flagged` | nullable boolean | — | Moderator decision; null means no override. |
| `override_reason` | nullable string | Unicode scalar values | Required when `override_flagged` is not null; empty/whitespace is invalid. |
| `analyzed_at` | timestamp with time zone | UTC | Required; latest assessment time. |

The source normalized text is read from the existing `intake_records` table but
is not copied into the assessment. Duplicate comparison is exact equality of
normalized text within the inclusive preceding 24-hour window. A burst is more
than five submissions in the inclusive preceding 10-minute window. A bot-like
repeat is more than three exact repeats in the supplied recent history. Term
lists are configured; matching is case-insensitive substring matching.

Default score weights are deterministic and configuration-overridable. The
assessment score is the sum of triggered signal weights, capped to `[0,1]`,
and `score >= 0.70` flags the case. This keeps the score explainable and
avoids treating it as a hidden model probability.

## API projection

- `GET /cases/{case_id}/abuse` is ADMIN/moderator-only and returns the current
  flag, score, signals, and effective decision. It never returns raw model
  output or a citizen-facing aggression judgment.
- `POST /cases/{case_id}/abuse-override` is ADMIN/moderator-only. It accepts a
  boolean decision and mandatory non-empty reason, updates only the current
  projection, and appends the BX-00 `spam_decision` event.

The endpoint shapes are defined by
`contracts/schemas/case-abuse-result.schema.json` and
`contracts/schemas/case-abuse-override-result.schema.json`.

## Invariants and race handling

- `0 <= risk_score <= 1`; `risk_score >= 0.70` means `label=flagged` when no
  moderator override exists.
- A clear/flagged assessment never changes case state, creates a ban, or
  exposes a user-facing accusation.
- A moderator override always has a non-empty reason and is represented in the
  immutable action log.
- Concurrent orchestrator passes use one upsert per case; a later pass may
  refresh the automatic assessment but must preserve an existing override.
- Concurrent overrides lock the assessment row; the last committed valid
  override is the effective decision and each accepted mutation has an audit
  event.
- Missing assessment returns `404 ABUSE_ASSESSMENT_NOT_FOUND`, not a guessed
  clear result.

## Decision D-BX04-01

| Option | Choice | Why |
|---|---|---|
| New abuse-analysis service | No | Adds topology for deterministic, case-local review metadata. |
| Workflow SQL projection + pure analyzer | **Yes** | Reuses the existing case lifecycle, is falsifiable in unit tests, and persists durable state. |
| Mandatory LLM classifier | No | Requirements make model use optional and require safe fallback. |
| CAPTCHA/ban/block pipeline | No | Explicitly outside the approved scope. |
| Raw inference/event stream retention | No | Conflicts with short-signal-only and no long-lived raw inference policy. |

## Verification predicates

- exact normalized duplicate at 24 hours flags; at 24 hours plus epsilon it does not;
- sixth submission in 10 minutes flags; fifth does not;
- fourth exact bot repeat flags; third does not;
- configured profanity/threat/harassment terms match case-insensitively;
- criticism, negative wording, and capitalization alone produce no signal;
- configured scores at `0.70` flag and at `0.70 - epsilon` remain clear;
- malformed optional model output is ignored/rejected and never persisted;
- unauthorized read/override is rejected; override without a reason is rejected;
- override persists and emits one `spam_decision` action event.
