import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiFetch,
  getAccessToken,
  refreshAccessToken,
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

describe("silent re-login (US-19)", () => {
  const expiredBody = { error: { code: "not_authenticated", message: "x" } };
  const expired = [401, expiredBody];
  const refreshed = { access_token: "new", token_type: "bearer", expires_in: 3600 };

  function headersOf(init: RequestInit | undefined): Record<string, string> {
    return (init?.headers ?? {}) as Record<string, string>;
  }

  it("refreshes an expired token once and retries the request with the new one", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setAccessToken("old");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname;
      if (path === "/api/v1/auth/refresh") return new Response(JSON.stringify(refreshed));
      const fresh = headersOf(init).Authorization === "Bearer new";
      return fresh
        ? new Response(JSON.stringify({ id: "p1" }))
        : new Response(JSON.stringify(expiredBody), { status: 401 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/projects/p1")).resolves.toEqual({ id: "p1" });
    expect(getAccessToken()).toBe("new");
    expect(handler).not.toHaveBeenCalled();
    const refreshCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/refresh"));
    expect(refreshCall?.[1]).toMatchObject({
      method: "POST",
      credentials: "include",
      headers: { "X-Requested-With": "rcd" },
    });
  });

  it("ends the session when the refresh cookie is gone too", async () => {
    mockApi({
      "GET /api/v1/projects/p1": expired,
      "POST /api/v1/auth/refresh": [401, { error: { code: "session_expired", message: "x" } }],
    });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setAccessToken("old");

    await expect(apiFetch("/projects/p1")).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledOnce();
  });

  it("shares one refresh between concurrent callers", async () => {
    const { calls } = mockApi({ "POST /api/v1/auth/refresh": refreshed });

    const tokens = await Promise.all([refreshAccessToken(), refreshAccessToken()]);

    expect(tokens).toEqual(["new", "new"]);
    expect(calls.filter((call) => call.path === "/api/v1/auth/refresh")).toHaveLength(1);
  });

  it("answers null instead of throwing when the server is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(refreshAccessToken()).resolves.toBeNull();
  });

  it("does not try to refresh a failed sign-in", async () => {
    const { calls } = mockApi({ "POST /api/v1/auth/login": expired });
    setAccessToken("old");

    await expect(
      apiFetch("/auth/login", { method: "POST", form: new URLSearchParams() }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(calls.map((call) => call.path)).toEqual(["/api/v1/auth/login"]);
  });

  it("sends credentials only to the cookie routes", async () => {
    const { fetchMock } = mockApi({
      "POST /api/v1/auth/login": refreshed,
      "GET /api/v1/workspaces": [],
    });

    await apiFetch("/auth/login", { method: "POST", form: new URLSearchParams() });
    await apiFetch("/workspaces");

    const [login, other] = fetchMock.mock.calls.map(([, init]) => init as RequestInit);
    expect(login.credentials).toBe("include");
    expect(other.credentials).toBeUndefined();
  });
});
