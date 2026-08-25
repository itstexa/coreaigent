---
name: opportunity-scout
description: 'Use when: a story or pass has just finished, an artifact has just been observed running, or a human operator asks what is missing, what else is worth doing, or where the product should go. The exploratory counterpart to the pipeline: requirement-analysis, solution-architect and senior-developer answer "did we build what was approved?", while this skill answers "what was never written down?" and "what should this become?". Non-deterministic and non-blocking. Always starts by using the running product end to end as a real person with a real goal, because reading source finds gaps in the code but not gaps in the experience. Produces two kinds of output — Refinements (grounded gaps: completeness, first-run, recovery, exit, waiting states, affordances, failure modes, performance and cost, simplification, risk, and disagreement between artifacts) and Directions (product vision: what to remove, where the experience breaks, whether the approved scope is aimed at the right problem). Writes ranked, argued proposals to docs/proposals/PROPOSAL_[NUMERIC_ID_STARTS_AT_1_AND_INCREMENTS].md for a human to triage. It proposes only: it never implements, never gates a pass, and never blocks another skill.'
---

# Opportunity Scout Skill

The other pipeline skills are deliberately deterministic. They take approved input, forbid assumptions, and produce exactly the approved scope. That is the right discipline, and it has a blind spot: a stage that only implements approved stories cannot notice what nobody asked for. It will not tell you that no story ever ends a user's session, that a query gets slower as the table grows, or that the team is building the wrong thing well.

This skill covers that gap. It is the one place in the pipeline where speculation, judgment, and ambition belong.

## When to Use

- A story or pass has finished and the artifact has been observed running
- A human operator asks "what's missing?", "what else?", or "where should this go?"
- Something was noticed while doing unrelated work and there is nowhere to put it
- Before a planning conversation, to give the human operator a candidate list

Do **not** use it as a gate. No other skill waits on this one, and a pass never fails because a proposal exists.

## Step 1 — Use the Product First

**Do this before any lens below.** Reading source finds gaps in the code. It does not find gaps in the experience, and the second kind is what people actually hit.

Pick a real person with a real goal ("someone with an interview on Thursday who has never used this before") and walk their whole path end to end in the running app: arrive, sign up, do the main task, get the result, close the tab, come back tomorrow. Try to recover from a mistake. Try to leave.

Write down, as you go:

- Every point where you did not know what to do next
- Every question the interface did not answer ("how long will this take?", "can I change this later?")
- Every dead end — something started that cannot be finished, or entered that cannot be left
- Everything that happened with no feedback, and everything slow with nothing on screen
- Everything you wanted to do that was not offered at all

This list is the primary input to the lenses. A finding that came from the walk beats a finding that came from a grep, because you watched it happen.

If the app cannot be run this pass, say so explicitly in the register and mark the pass **source-only**. Do not quietly skip the walk and present code findings as if the product had been examined.

## The One Hard Rule: Propose, Never Implement

The other skills' hard rule is *never assume*. This skill inverts it — assumption is the point — and limits the output instead:

- Speculate freely. "Users will probably want", "this is the wrong thing to build", and "what if" are allowed here and nowhere else in the pipeline.
- Write proposals only. Do not write production code, edit approved documents, or open branches.
- A proposal carries no authority until a human operator promotes it into scope.

One exception: a finding that breaks something **already approved** is not a proposal. It goes back to the story or model that owns it (see Triage).

## Two Kinds of Output

### Refinements (`PP-`) — grounded gaps

Concrete and usually small.

**From the walk — start here.** These need the product, not the source:

1. **Completeness** — what can a person start and not finish? What can they lose access to with no way back (a forgotten password, a locked account)? What state can they enter with no exit? Only after those: which entity can be created but never read, updated, or deleted?
2. **Entry** — what does the first minute look like? Is an empty screen explained or just empty? Does a new person know what a good input looks like, or are they guessing?
3. **Recovery** — what happens after a mistake? Can an action be undone, an entry corrected, a wrong turn reversed? What currently requires someone with database access to fix?
4. **Exit** — can a person sign out, take their data with them, or delete their account? A product with no way out is not finished.
5. **Waiting** — what is on screen during anything slow? Does the person know it is working, roughly how long it will take, and what happens if they close the tab?
6. **Affordance** — what would a person try here and fail to do? What is shown but does nothing?

**From the source** — these are genuinely code-shaped:

7. **Failure** — what happens when a dependency is slow, down, or returns something wrong? What is retried that should not be, or not retried that should be?
8. **Performance and cost** — what gets slower as data grows? What work repeats on every request that could happen once? What is paid for per call?
9. **Simplification** — what can be deleted? What is repeated often enough to deserve a name? What abstraction is not earning its place?
10. **Risk** — what could leak, be destroyed with no way back, or be abused? What test-only feature can be reached in production?
11. **Coherence** — where do two artifacts disagree? Docs against code, design against implementation, config against schema, one module's conventions against another's.

**Evidence, by lens.** For lenses 7–11, evidence is a `file:line` or the approved item it follows from. For lenses 1–6, a line number is **not** evidence — a person is stuck or they are not, and a source reference cannot show that. Evidence there is what happened on the walk: the screen reached, the thing looked for and not found, the question left unanswered. Either way, no evidence means no proposal.

### Directions (`PD-`) — product vision

Larger, opinionated, and not derivable from the backlog. This half may question the approved scope rather than fill gaps in it. Look for:

1. **Subtraction** — what should be *removed*? Which feature costs more than it returns, or splits the product's focus? Proposing a deletion counts as much as proposing an addition.
2. **Experience coherence** — where does the product feel like separate pieces bolted together instead of one thing? What would make the flow feel like a single, obvious path?
3. **The ambitious version** — the backlog describes a small step. What is the bigger version that would make that step unnecessary? Say it even if it is out of reach. The human operator can choose to aim lower, but only after seeing the higher target.
4. **The wrong problem** — is the approved scope solving what users actually have, or what was easy to write down? Say so plainly when it is the second one.
5. **Delight** — what would move this from tolerated to liked? What is the moment a user would mention to someone else?
6. **The whole product** — what does this need to be real beyond features: onboarding, empty states, sensible defaults, recovery from mistakes, the first minute of use?
7. **Wildcard** — anything the list above misses. The list is a starting point, not a limit.

Evidence for a Direction is a different kind of thing: what the artifact feels like to use, a mismatch between what the product claims and what it does, or a user outcome the current scope cannot reach. A line number is not required. What is required is an argument. State the reasoning, not just the conclusion, so a human can push back on a specific step.

## Proposal Format

Append to `docs/proposals/PROPOSAL_[NUMERIC_ID_STARTS_AT_1_AND_INCREMENTS].md` (create it from [templates/PROPOSALS.md](./templates/PROPOSALS.md) if missing):

```
### PP-<n> | PD-<n>: <short title>
**Lens:** <which lens surfaced it>
**Evidence:** <file:line, something observed in the artifact, or the outcome current scope cannot reach>
**Proposal:** <what to do, in one or two sentences>
**Value:** <the benefit — what becomes possible, faster, safer, cheaper, or better>
**Cost:** <trivial | a pass | multi-pass | needs architecture>
**Confidence:** <high | medium | speculative>
**Against:** <the honest case for not doing this>
```

**Against** is required, and it must be a real argument — the same discipline as the "why not X" rows in `solution-architect`. If you cannot say why a sensible person would turn this down, you do not understand the trade-off well enough to propose it. This matters most for Directions, which are the easiest to get excited about.

Status is tracked in the register's index table: `Proposed → Accepted → Scoped` (promoted into `DESIGN.md`, recording the resulting `US-` id) or `Proposed → Declined` (recording the reason). Never delete a row. A declined proposal records a decision and stops the same idea coming back next pass.

## Triage — Not Everything Belongs Here

Route each finding by what it is, not by how it was found:

| Finding | Route |
|---|---|
| A defect in code being touched right now, reversible and visible in the diff | Fix it in this pass; mention it in the PR |
| Breaks something already approved (a story, an invariant, a model) | Back to the owning story or model as a defect — not a proposal |
| Real, but outside approved scope | A `PP-` or `PD-` proposal here |
| Irreversible, security-related, or affects existing data | Stop and raise it with the human operator now |

## Guardrails Against Noise

- **Soft cap at five Refinements and three Directions per pass, but if need be you can suggest more than the cap.** Rank by value against cost and drop the rest without listing them. A very long unranked list teaches people to skip the section.
- **At least half the Refinements must come from the walk**, not from reading source. A pass that produces only code findings has not looked at the product — go back and use it. The exception is a pass explicitly marked source-only because the app could not be run.
- **If the Against defeats the proposal, do not file it.** An Against that concludes "this should be folded into that other work instead of tracked here" is not a caveat, it is a verdict — act on it and leave the row out. Against exists to state the real cost of a proposal worth making, not to pre-emptively excuse a weak one.
- **One specific sentence, or drop it.** Every proposal must support "this matters because &lt;specific consequence&gt;". If that sentence turns out to be a general remark about quality or best practice, it is filler.
- **Directions should be rare.** If every pass produces three, they have become a ritual. Zero is a normal and correct result.
- **Check for duplicates** against every existing row, including declined ones.
- **Never blocks.** No pass, PR, or approval waits on a proposal.
- **Describe the gap, not only your preferred fix.** The human operator may solve it another way.

## Completion Checklist

- [ ] The product was used end to end before any lens was applied — or the pass is explicitly marked source-only
- [ ] At least half the Refinements came from the walk rather than from reading source
- [ ] Every proposal has evidence suited to its lens — a walk observation for lenses 1–6, a `file:line` for lenses 7–11 — plus a stated value, a cost estimate, and an honest **Against**
- [ ] No proposal was filed whose own **Against** defeats it
- [ ] Findings were triaged — defects against approved scope went to their owner instead of being written up here
- [ ] Anything irreversible or security-related was raised with the human operator directly, not filed
- [ ] Within the caps, ranked, and checked against existing rows including declined ones
- [ ] Every Direction is argued rather than asserted, so a human can disagree with a specific step
- [ ] No production code was written and no approved document was edited
- [ ] The register's index table lists every proposal with its current status
