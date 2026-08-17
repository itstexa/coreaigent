# Agent guidance

## Docker verification

Use the Docker commands in [README.md](README.md#docker-test-commands) for the
repository's baseline contract and mock E2E verification. The documented mock
suite is the required check for changes to Compose files, contracts, mocks,
scenarios, or test code.

Do not present a mock as a real service: `dev`, `integration`, and `e2e`
require the service implementation and/or immutable real image tags described
in the README.
