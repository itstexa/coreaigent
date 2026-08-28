# Architecture Session — BX-06 validation preview

> Consumes approved [BX-06 design](../design/DESIGN_bd84424_extensions.md).
> Scope is only the two approved preview scenarios. Submission timing, draft
> saving, and direct field editing remain blocked by OQ-183 through OQ-185.

## Component Boundary

`frontend/src/PetitionForm.tsx` renders the validation result already returned
by the intake flow. The preview is a read-only projection of F-03
`ValidationResultV3`; `validation` remains the source of truth. No database,
worker, endpoint, contract, or AI call is added.

```text
runIntake result
  └── CaseRecord.validation: ValidationResultV3 | null
        └── PetitionForm preview
              ├── missingRequiredFields / invalidFields labels
              └── unavailable state when validation is null
```

## Data Models

### Entity: ValidationPreviewProjection

Traces to: BX-06 ([DESIGN_bd84424_extensions.md](../design/DESIGN_bd84424_extensions.md))

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `validation` | `ValidationResultV3 \| null` | — | Current intake-flow result; null means no result is available to this page. |
| `missingRequiredFields` | array of `{id:string,label:string}` | field entries | Read unchanged from non-null `validation`; may be empty. |
| `invalidFields` | array of `{id:string,label:string,code:string}` | field entries | Read unchanged from non-null `validation`; may be empty. |
| `availability` | enum | — | `available` when `validation` is non-null; `unavailable` otherwise. |

**Invariants**

- Every displayed missing/invalid label originates in the current
  `ValidationResultV3`; the frontend does not infer, translate, or fabricate a
  required field.
- `validation = null` displays an unavailable/pending explanation and no field
  list.
- The projection makes no write and cannot alter F-03 state or its revision.

**Boundary Behavior**

- Min/Max: zero missing and zero invalid fields are valid and display no gap;
  F-03 owns all cardinality limits.
- Empty/Null/Zero: null validation produces unavailable state; an empty
  `label` would be invalid F-03 producer output and is not replaced with a
  client-generated label.
- Overflow/Truncation: the browser does not truncate or synthesize preview
  entries; schema/transport limits remain owned by F-03.

**Concurrency / Race-Scenario Analysis**

- A completed intake or supplemental response replaces the single React
  `validation` value atomically. The preview reads one value, never combines
  missing fields from one result with invalid fields from another.
- The preview is read-only. Concurrent F-03 updates remain governed by the
  existing `If-Match` and idempotency rules; this feature adds no client retry.

## Technology / Design Decisions

### Decision D-BX06-01: Reuse the in-flow F-03 result

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Render `CaseRecord.validation` in `PetitionForm` | Uses current typed F-03 result; no API, persistence, or duplicate validation logic. | Available only where intake/supplement responses provide that result. | ✅ |
| Add a BX-06 preview endpoint | Could support a later standalone view. | Duplicates F-03 state/projection before OQ-183 establishes that need. | ❌ |
| Recalculate missing fields in the browser | Could render without a result. | Violates F-03 ownership and can invent a field. | ❌ |

**Why the first option:** It satisfies both approved scenarios with the
existing authoritative result and smallest surface.

**Why not a preview endpoint:** No approved standalone/cross-session preview
requirement exists.

**Why not browser recalculation:** Field rules belong to the versioned F-03
registry and backend validation.

## Verification

- Add frontend tests proving labels from a supplied `ValidationResultV3` render
  in the preview.
- Add a negative test proving `validation: null` renders unavailable wording
  and no guessed field label.
- No contract or Docker suite change is required unless implementation changes
  a service boundary.

## Open Questions

No architecture question is needed for the approved in-flow preview. OQ-183
through OQ-185 remain requirement-level blockers for broader BX-06 scope.
