# Design Session — US-113 F-09 implemented case API contract atlas

> Consumes [F-09 API contract stabilization](../tekno_agent_feature_pack/09_api_contracts.md)
> against the already implemented F-03 through F-06 routes.

## User Story

### US-113: Versioned public case API contract atlas

As an API consumer and CI maintainer
I want the repository contract manifest and JSON Schemas to cover every
implemented public case-level operation
So that clients, Docker tests, and code share one verifiable endpoint contract.

## Acceptance Criteria

Feature: F-09 implemented case API contract atlas

  Scenario: Contract validation covers implemented case endpoints
    Given the workflow and validation services expose their implemented public routes
    When the JSON contract manifest is validated
    Then it includes the F-03 supplemental PATCH, F-04 correspondence POST/GET,
    F-05 routing GET, F-06 case GET, and F-06 review-completion POST routes
    And every endpoint references strict request and response schemas

  Scenario: Current correspondence result remains revision-safe
    Given a current case revision has no generation or has queued, processing,
    completed, or failed correspondence work
    When its GET response is validated against the documented schema
    Then `not_requested` exposes `result: null`
    And terminal success includes only the implemented citation/result fields
    And failure exposes no partial draft

  Scenario: Contract validation rejects an invented or incomplete endpoint
    Given an endpoint references a missing schema, has an unsupported method,
    or omits a required current-result branch
    When the contract checks run
    Then validation fails before a Docker scenario can claim compatibility

## Open Questions

None. The F-09 artifact is stabilization of already implemented HTTP behavior;
route ownership and response semantics are established by approved F-03–F-06
contracts and their real acceptance tests.
