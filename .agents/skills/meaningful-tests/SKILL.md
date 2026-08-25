---
name: meaningful-tests
description: 'Use when: writing new unit/integration tests, or reviewing/auditing existing tests for quality. Applies a falsification-driven discipline — tests must be able to fail when the code is wrong, not just pass — checking for at least 7 failure modes (happy-path-only, vacuous, derived-from-code, structural-only, over-mocked, near-boundary, missing-negative/zero-assertion) and requiring boundary tests to assert the exact limit plus limit ± epsilon.'
---

# Meaningful Tests Skill

Tests exist to falsify — to try to prove the code wrong and fail when it is. A test suite that only ever passes is not evidence of correctness. Use this discipline whenever writing new tests or reviewing/auditing existing ones (unit or integration).

## When to Use

- Writing new unit or integration tests for a change
- Reviewing a PR's tests, or auditing an existing test file/suite for quality
- A test suite is green but confidence in the code is still low ("false sense of security")

## Core Rule: Falsification, Not Confirmation

For every test, ask: **"If the implementation had a subtle bug right here, would this test actually fail?"** If the answer is no, the test isn't meaningful yet — rewrite it. Test expectations must come from the spec/requirement/contract (what the code is *supposed* to do), never from running the implementation and copying whatever it happened to output.

## The 7 Failure Modes to Check For

Run this checklist against each test file/suite under review (or as you write new ones):

1. **Happy-path-only** — every test exercises only the success/normal-input case. Fix: add at least one test per behavior for an error, edge, or unusual-but-valid input.
2. **Vacuous** — the assertion can't meaningfully fail (`assertTrue(true)`, asserting only that "no exception was thrown" with no value check, asserting a mock was called without checking its arguments, a snapshot test no one has actually read). Fix: assert a specific, checkable expected value or state.
3. **Derived-from-code** — the expected value was obtained by running the implementation and pasting its output, rather than from the spec/AC. Fix: derive expectations independently (from requirements/ACs, a spec, or hand-computed values) before running the code.
4. **Structural-only** — the test checks shape/type/presence only ("result is not null", "list has length 3", "response has a `data` field") without checking the actual content/values. Fix: assert on the real content, not just its shape.
5. **Over-mocked** — so much of the unit under test is mocked/stubbed that the test exercises the mocks, not the code. A smell: mocks return canned values that make the assertion trivially true. Fix: mock only true external boundaries (network, disk, time, randomness, other services) — never the logic actually being tested.
6. **Near-boundary gaps** — limits, thresholds, and edges of ranges are untested. Fix: see Boundary Convention below.
7. **Missing negative/zero-assertion** — empty, zero, `null`/`None`, or negative inputs are never exercised, or when they are, nothing is actually asserted about the resulting behavior (just "didn't crash"). Fix: explicitly assert what *should* happen for empty/zero/negative input (rejection, a defined default, a specific error), not merely the absence of a crash.

## Boundary-Test Convention

For every limit/threshold `L` the code enforces or depends on, write tests at:
- **Exactly `L`** — confirms the inclusive/exclusive behavior at the boundary itself
- **`L − epsilon`** — just inside the valid/expected side
- **`L + epsilon`** — just outside, on the other side of the boundary

`epsilon` is the smallest meaningful increment for the type: `1` for integers/counts, the smallest representable difference for floats, `1ms`/`1` unit for time or size limits. All three assertions must check the actual expected outcome (accept vs. reject, included vs. excluded), not just "no error."

## Procedure

1. Identify the behavior/contract under test — pull expectations from the requirement/AC/spec, not from the implementation.
2. Write or review the tests, running each one through the 7 failure modes above.
3. For every limit/threshold in scope, apply the Boundary-Test Convention (limit, limit−epsilon, limit+epsilon).
4. For each mocked dependency, confirm it's a true external boundary, not internal logic being tested.
5. For each assertion, apply the falsification question: would this test fail if the code had a subtle bug at this exact point?
6. Flag and fix any failure mode found; do not mark the review/authoring complete until all 7 have been checked.

## Completion Checklist

- [ ] At least one non-happy-path test exists per behavior (error, edge, or unusual-valid input)
- [ ] No assertion is vacuous — every one can fail given a wrong implementation
- [ ] Expected values came from the spec/AC, not from copying the implementation's output
- [ ] Tests assert actual content/values, not just shape/type/presence
- [ ] Mocks are limited to true external boundaries; the unit under test is genuinely exercised
- [ ] Every limit/threshold has tests at the limit, limit−epsilon, and limit+epsilon, each with a real assertion
- [ ] Empty/zero/null/negative inputs are exercised with an explicit assertion on expected behavior, not just "no crash"
