# CI wiring

`.github/workflows/pr-contract-tests.yml` runs on every pull request. It
validates the Compose configuration, builds and starts the mock services, and
runs the contract-test container in mock mode. That command validates the JSON
Schemas and executes all golden scenarios before the runner tears down the
Compose resources.

When real services exist, extend this workflow with their service-owned unit
tests. On the main branch, build and publish every implemented service as
`ghcr.io/<org>/coreaigent-<service>:<commit-sha>`, set the immutable image
variables, then run `scripts/coreaigent.ps1 e2e` and
`tests/run_scenarios.py --mode real`.

Never publish or consume `latest`; the mock image is versioned as `coreaigent/contract-mock:1.0` and production-compatible images use commit SHA tags.
