import { describe, expect, it } from "vitest";
import { ApiError, apiErrorMessage, scenarioAwareError } from "./api";

describe("apiErrorMessage", () => {
  it("maps revision conflicts to a recoverable UI instruction", () => {
    const error = new ApiError("raw", 412, "CASE_REVISION_CONFLICT", false);
    expect(apiErrorMessage(error)).toContain("Güncel durumu");
  });

  it("keeps an unknown backend message", () => {
    const error = new ApiError("Özel backend mesajı", 409, "CUSTOM", false);
    expect(apiErrorMessage(error)).toBe("Özel backend mesajı");
  });
});

describe("scenarioAwareError", () => {
  const rejection = new ApiError(
    "Invalid request, unknown scenario, or endpoint",
    400,
    "validation",
    false,
    undefined,
    "mock",
  );

  it("explains the golden-scenario requirement for unbound free text", () => {
    const mapped = scenarioAwareError(rejection, undefined) as ApiError;
    expect(mapped.code).toBe("MOCK_SCENARIO_REQUIRED");
    expect(apiErrorMessage(mapped)).toContain("golden senaryo");
  });

  it("keeps the backend message when a golden document was submitted", () => {
    expect(scenarioAwareError(rejection, "doc-s05-gurultu-sikayeti")).toBe(rejection);
  });

  it("keeps real-service validation errors untouched", () => {
    const real = new ApiError("Ham servis mesajı", 400, "validation", false, undefined, "real");
    expect(scenarioAwareError(real, undefined)).toBe(real);
  });
});
