// The one HTTP client (Pranshu). Every request goes through apiFetch so the token, the error
// shape and the "session expired" handling are the same everywhere. Feature folders wrap it in
// TanStack Query hooks (features/<area>/api.ts); components never call fetch directly.

import type { ApiErrorBody } from "./types";

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

// US-19: the token lives in memory only (never localStorage), set by the AuthProvider.
let accessToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

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
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.form) {
    body = options.form; // the browser sets the multipart / urlencoded content type
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path, options.query), {
      method: options.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "Cannot reach the server. Check your connection.");
  }

  if (!response.ok) {
    const error = await toError(response);
    if (response.status === 401 && accessToken) {
      onUnauthorized?.();
    }
    throw error;
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
