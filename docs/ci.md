# CI wiring

`.github/workflows/pr-contract-tests.yml` runs on every pull request. It first
runs the repository's falsification-focused Python tests on CPU, then validates
the Compose configuration, builds and starts the mock services, and
runs the contract-test container in mock mode. That command validates the JSON
Schemas and executes all golden scenarios before the runner tears down the
Compose resources.

The same workflow also runs the real OCR development overlay with PostgreSQL.
It executes the F-01 acceptance runner before and after an OCR container
restart, then runs the normal 58-scenario development flow with only OCR real.
The baseline mock job remains separate and does not start PostgreSQL.

The `classification-durable-worker` job layers the real classification API and
worker over that real OCR/PostgreSQL topology. It verifies the v3 classification
contract and that durable outbox work reaches a single current PostgreSQL
classification before the job is marked complete. Validation, RAG, LLM, and
workflow remain mocks in this development-scoped job.

The `validation-current-state` job layers the real validation API over that
same PostgreSQL topology. It uses the explicitly injected deterministic
extractor to make CPU CI repeatable; therefore it verifies F-03 contracts,
current-only state, missing/invalid separation, ETag preconditions, and
idempotent replay, not GPU Jamba inference. A separate GPU run with
`EXTRACTOR_MODE=jamba` is required to smoke the real semantic extractor path.

GitHub-hosted PR runners do not provide the pinned model cache and NVIDIA GPU
needed for honest F-04–F-06 Jamba/BGE-M3 verification. This workflow therefore
does not label a mock LLM flow as a real workflow run. Run the full local
command in [README.md](../README.md#docker-test-commands) on a GPU host; it
executes real Jamba, BGE-M3, PostgreSQL workers and the F-04–F-06 runners.

When real services exist, extend this workflow with their service-owned unit
tests. On the main branch, build and publish every implemented service as
`ghcr.io/<org>/coreaigent-<service>:<commit-sha>`, set the immutable image
variables, then run `scripts/coreaigent.ps1 e2e` and
`tests/run_scenarios.py --mode real`.

Never publish or consume `latest`; the mock image is versioned as `coreaigent/contract-mock:1.0` and production-compatible images use commit SHA tags.
