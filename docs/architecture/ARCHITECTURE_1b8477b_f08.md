# Architecture Session — US-112 F-08 truthful local Compose modes

> Consumes approved [F-08 design](../design/DESIGN_f38fa41_f08.md).

## Component boundary

F-08 changes only the developer-mode composition and its verification command.
It does not replace the mandatory deterministic mock baseline, alter public
service contracts, or make a remote image appear local. `dev <service>` and
`test development <service>` resolve a declarative local dependency closure;
each existing implementation in that closure is built from this checkout.

```text
selected service
       |
       v
local topology registry ──> ordered Compose overlays ──> local services
       |                                                    |
       +----------------------> named real acceptance runner+

no local implementation ──> explicit mixed topology / fail before a false
                              "real" claim
```

## Data Models

### Entity: LocalDevelopmentTopology

Traces to: US-112 (docs/design/DESIGN_f38fa41_f08.md)

| Field | Type | Unit | Constraints |
|---|---|---|---|
| `service` | service-id string | — | One of the wrapper's supported services; unique registry key. |
| `compose_files` | ordered array of repository-relative paths | files | Starts with `compose.yaml`; every listed overlay must exist. |
| `local_services` | array of service-id strings | services | Every member has a local Dockerfile and is built from this checkout. |
| `verification_kind` | enum | — | `real_local` or `mixed_local`; it is shown in command output. |
| `acceptance_runner` | ordered command array | argv | Real-local modes name a non-mock test runner; it executes inside `contract-tests`. |
| `missing_dependencies` | array of service-id strings | services | Empty for `real_local`; non-empty only for explicit `mixed_local` modes. |

**Invariants** (must always hold true):

- A `real_local` topology contains every runtime dependency that has a local
  implementation; Compose overlays build those services locally rather than
  retaining their base mock definitions.
- `test development` invokes the topology's named acceptance runner, never
  `run_scenarios.py --mode development`, when the closure contains more than
  the selected service.
- A topology with a missing implementation is labelled `mixed_local`; it is
  never described as full real end-to-end verification.

**Boundary Behavior:**

- Min/Max: a topology has at least base Compose plus one local overlay and one
  acceptance command; no arbitrary user-supplied overlay or runner is loaded.
- Empty/Null/Zero: an unknown service, absent topology, Dockerfile, overlay,
  GPU, or required model cache fails before Compose starts a claimed real mode.
- Overflow/Truncation: wrapper arguments remain discrete service IDs and file
  names; they are rejected rather than interpolated into shell text.

**Concurrency / Race-Scenario Analysis:**

- Each invocation creates its own transient generated override only for modes
  that need a selected local image. Compose's project-level resource names
  remain its normal concurrency boundary; F-08 does not share mutable test
  results or claim cross-invocation isolation.

### Predicate: FullLocalDependencyClosure

| Input | Type | Unit | Constraint |
|---|---|---|---|
| `selected_service` | service-id string | — | Supported local service. |
| `required_services` | directed dependency set | services | Transitive runtime dependencies needed for its real workflow path. |
| `local_implementation(service)` | boolean | — | True only when the service has a checked-in Dockerfile. |
| `mode` | enum | — | `real_local` iff every required service has a local implementation and runtime prerequisite. |

**Invariants** (must always hold true):

- OCR uses PostgreSQL; classification adds OCR and its durable worker;
  validation adds OCR, classification, PostgreSQL, real Jamba extraction, and
  its GPU/cache overlay; workflow adds every preceding service plus BGE-M3 and
  the workflow workers.
- The mock baseline remains a separate `test mock` path and starts no
  PostgreSQL, BGE-M3, or Jamba implementation.

**Boundary Behavior:**

- A missing GPU/readiness/cache for a topology that requires Jamba is a failed
  local prerequisite, not permission to substitute the LLM mock.
- The standalone `rag` selection has no Dockerfile; it fails with the existing
  clear missing-implementation message. F-04 retrieval remains owned by the
  local workflow image and does not turn `rag` mock into a standalone real
  service.

**Concurrency / Race-Scenario Analysis:**

- Multiple worker replicas in a full topology use their existing PostgreSQL
  leases. F-08 only starts them together; it does not change durable-job
  ownership or retry predicates.

## Decisions

### Decision D-170: Declarative dependency-closure registry

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| One repository-owned topology registry consumed by the PowerShell wrapper and checked by tests | Keeps overlay order, truth label, and runner reviewable as data. | Adds a small registry file. | ✅ |
| Add independent `if` chains for each command branch | Small immediate edit. | `dev` and `test development` can silently drift again. | ❌ |
| Make every command start all services indiscriminately | Simple mental model. | Starts unrelated GPU/model workloads and hides selected-service scope. | ❌ |

**Why the registry:** one declared closure drives both start and verification
behavior, so a new service cannot accidentally receive a mock-only test path.

**Why not independent branches:** duplicated composition logic caused the
current F-08 mismatch.

**Why not every service:** the approved requirement is the selected service's
dependency closure, not unrelated workloads.

### Decision D-171: Real-model validation verification

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Full local validation/workflow topology sets `EXTRACTOR_MODE=jamba` and asserts real service contracts plus persisted state | Exercises actual Jamba extraction without asserting unstable prose. | Requires GPU/cache and may need supplemental completion when semantic extraction omits a field. | ✅ |
| Reuse the CPU deterministic extractor under a full-real label | Fast and stable. | Does not meet the real-local Jamba requirement. | ❌ |
| Assert an exact Jamba JSON string | Simple-looking fixture. | Model sampling/format variation makes it a false reliability oracle. | ❌ |

**Why contract/state assertions:** the local Jamba endpoint, validation API,
PostgreSQL current state, and downstream workers are all actual components;
their stable behavior is structural contract and durable state, not a copied
model sentence.

**Why not deterministic extraction:** it remains useful and explicitly named
for CPU F-03 coverage, but cannot prove the real Jamba path.

**Why not exact output:** it would test a brittle incidental completion rather
than whether the service handled a valid structured model result safely.

### Decision D-172: Missing prerequisite handling

| Option | Benefits | Drawbacks | Chosen |
|---|---|---|---|
| Stop before startup when a required local implementation or real runtime prerequisite is unavailable; label only genuinely missing dependencies as mixed | Truthful operator result and no hidden mock substitution. | Operator must provision the prerequisite. | ✅ |
| Quietly fall back to the base mock | Lets a command finish. | Directly misrepresents the requested real verification. | ❌ |
| Remove every mock fallback | Uniform claims. | Prevents legitimate mixed development where a dependency genuinely has no local implementation. | ❌ |

**Why stop/label:** it implements the approved distinction between an available
local closure and a specifically disclosed mixed topology.

**Why not quiet fallback:** it violates the repository and operator contract.

**Why not remove all mocks:** explicit mocks remain useful where no local
service exists; their label is the safety boundary.

## Verification

- `test mock` continues to execute the README baseline scenario suite.
- `test development ocr`, `classification`, `validation`, `llm`, and `workflow`
  resolve named real-local runners. The validation and workflow topologies add
  the Jamba extraction override after the base validation overlay, so it wins
  over the CPU deterministic setting.
- Tests independently assert the registry's exact closure for every supported
  service, reject an absent Dockerfile/overlay as a false real mode, and verify
  that development tests select named runners rather than mock scenarios.
- Docker verification runs the mandatory README mock suite and, when local
  GPU/cache prerequisites are available, the full workflow command. Its result
  identifies it as a real local run; unavailable prerequisites fail explicitly.

## Architecture Open Questions

None. OQ-150 resolves the only topology choice; existing README policy defines
the stable real-model oracle as contract and durable-state assertions.
