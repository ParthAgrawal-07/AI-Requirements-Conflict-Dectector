// The one HTTP client (Pranshu). Every request goes through apiFetch so the token, the error
// shape and the "session expired" handling are the same everywhere. Feature folders wrap it in
// TanStack Query hooks (features/<area>/api.ts); components never call fetch directly.

import type { ApiErrorBody, TokenResponse } from "./types";

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

/** A failed request, with the backend's machine-readable code (e.g. "signup_refused"). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fieldErrors: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// US-19: the token lives in memory only (never localStorage), set by the AuthProvider. The
// long-lived credential is the refresh cookie: HttpOnly, so no script (and no XSS) can read it.
let accessToken: string | null = null;
let onUnauthorized: (() => void) | null = null;
let refreshing: Promise<string | null> | null = null;

// The routes that set or read the refresh cookie. They send credentials, and a 401 from them is
// an answer, not an expired token to refresh.
const COOKIE_ROUTES = ["/auth/login", "/auth/signup", "/auth/refresh", "/auth/logout"];
// A custom header forces a CORS preflight, so another site cannot fire refresh/logout with a
// plain form post (backend app/api/auth.py).
export const CSRF_HEADERS: Readonly<Record<string, string>> = { "X-Requested-With": "rcd" };

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Called once by the AuthProvider: what to do when the server says the token is no good. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export function triggerUnauthorized(): void {
  onUnauthorized?.();
}

/**
 * Trade the refresh cookie for a new access token (silent re-login). Concurrent callers share
 * one request — the cookie is single-use, so parallel refreshes would race. Resolves to `null`
 * when there is no usable session; the caller decides whether that means "sign in again".
 */
export function refreshAccessToken(): Promise<string | null> {
  refreshing ??= (async () => {
    try {
      const response = await fetch(apiUrl("/auth/refresh"), {
        method: "POST",
        credentials: "include",
        headers: { ...CSRF_HEADERS },
      });
      if (!response.ok) return null;
      const body = (await response.json()) as TokenResponse;
      accessToken = body.access_token;
      return body.access_token;
    } catch {
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: unknown;
  form?: FormData | URLSearchParams;
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
}

export function apiUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${API_PREFIX}${path}`, API_BASE_URL);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function toError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    const fields: Record<string, string> = {};
    for (const detail of body.error.details ?? []) {
      fields[detail.field] = detail.message;
    }
    return new ApiError(response.status, body.error.code, body.error.message, fields);
  } catch {
    return new ApiError(response.status, "http_error", response.statusText || "Request failed");
  }
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const cookieRoute = COOKIE_ROUTES.includes(path);
  const sentToken = accessToken;
  let response = await send(path, options, sentToken, cookieRoute);

  if (response.status === 401 && sentToken && !cookieRoute) {
    // Another call may have refreshed while this one was in flight: then just use its token.
    const token = accessToken !== sentToken ? accessToken : await refreshAccessToken();
    if (token) {
      response = await send(path, options, token, cookieRoute);
    }
    if (response.status === 401) {
      onUnauthorized?.();
    }
  }

  if (!response.ok) {
    throw await toError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function send(
  path: string,
  options: RequestOptions,
  token: string | null,
  cookieRoute: boolean,
): Promise<Response> {
  const headers: Record<string, string> = cookieRoute ? { ...CSRF_HEADERS } : {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.form) {
    body = options.form; // the browser sets the multipart / urlencoded content type
  }

  try {
    return await fetch(apiUrl(path, options.query), {
      method: options.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: options.signal,
      // Cross-origin, the browser stores and sends the refresh cookie only with "include".
      ...(cookieRoute ? { credentials: "include" as const } : {}),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "Cannot reach the server. Check your connection.");
  }
}
