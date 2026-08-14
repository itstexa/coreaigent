# CI wiring

The repository has no existing CI to modify. Add these jobs to the first workflow instead of introducing a second platform:

1. Pull requests: service unit tests, `tests/validate_contracts.py`, image build, `docker compose up --build`, then `python tests/run_scenarios.py --mode mock`.
2. Main: build and publish every implemented service as `ghcr.io/<org>/coreaigent-<service>:<commit-sha>`, set the immutable image variables, then run `scripts/coreaigent.ps1 e2e` and `tests/run_scenarios.py --mode real`.

Never publish or consume `latest`; the mock image is versioned as `coreaigent/contract-mock:1.0` and production-compatible images use commit SHA tags.

