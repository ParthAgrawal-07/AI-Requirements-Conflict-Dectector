import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiFetch,
  setAccessToken,
  setUnauthorizedHandler,
} from "../src/api/client";
import { mockApi } from "./test-utils";

afterEach(() => {
  setAccessToken(null);
  setUnauthorizedHandler(null);
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("sends the in-memory token and parses JSON", async () => {
    const { fetchMock } = mockApi({ "GET /api/v1/auth/me": { id: "u1" } });
    setAccessToken("tok");

    await expect(apiFetch("/auth/me")).resolves.toEqual({ id: "u1" });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("turns the backend error body into an ApiError with code and field errors", async () => {
    mockApi({
      "POST /api/v1/auth/signup": [
        422,
        {
          error: {
            code: "validation_error",
            message: "Request validation failed",
            request_id: "r",
            details: [{ field: "email", message: "not an email", type: "value_error" }],
          },
        },
      ],
    });

    const failure = await apiFetch("/auth/signup", { json: {} }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe("validation_error");
    expect((failure as ApiError).fieldErrors).toEqual({ email: "not an email" });
  });

  it("calls the unauthorized handler when a signed-in request gets 401", async () => {
    mockApi({ "GET /api/v1/auth/me": [401, { error: { code: "not_authenticated", message: "x" } }] });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setAccessToken("expired");

    await expect(apiFetch("/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledOnce();
  });

  it("reports a network failure as a readable error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiFetch("/auth/me")).rejects.toMatchObject({ code: "network_error" });
  });

  it("drops empty query values", async () => {
    const { calls } = mockApi({ "GET /api/v1/projects/p/requirements": { items: [] } });
    await apiFetch("/projects/p/requirements", { query: { q: "", state: "Approved", owner: undefined } });
    expect(calls[0].path).toBe("/api/v1/projects/p/requirements?state=Approved");
  });
});
