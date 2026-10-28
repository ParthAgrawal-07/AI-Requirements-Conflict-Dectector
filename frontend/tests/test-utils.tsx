import type { ReactElement, ReactNode } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../src/app/auth";
import { ToastProvider } from "../src/components/Toast";

/**
 * Shared render helper: the app's providers (TanStack Query, auth, toasts, router) around the
 * component. `route` is the URL to start at; `path` the route pattern that provides params.
 */
export interface ProviderOptions extends Omit<RenderOptions, "wrapper"> {
  route?: string;
  path?: string;
}

export function renderWithProviders(
  ui: ReactElement,
  { route = "/", path, ...options }: ProviderOptions = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function AllProviders({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AuthProvider>
            <MemoryRouter
              initialEntries={[route]}
              future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
            >
              {path ? (
                <Routes>
                  <Route path={path} element={children} />
                  <Route path="*" element={<p>navigated away</p>} />
                </Routes>
              ) : (
                children
              )}
            </MemoryRouter>
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    );
  }
  return {
    user: userEvent.setup(),
    queryClient,
    ...render(ui, { wrapper: AllProviders, ...options }),
  };
}

/** Replace fetch with a router of canned JSON answers: { "GET /api/v1/x": body | [status, body] }. */
export function mockApi(routes: Record<string, unknown>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    calls.push({ method, path: url.pathname + url.search, body: init?.body });
    const key = Object.keys(routes).find((candidate) => {
      const [m, p] = candidate.split(" ");
      return m === method && (url.pathname === p || url.pathname + url.search === p);
    });
    if (!key) {
      return new Response(JSON.stringify({ error: { code: "not_found", message: "no mock" } }), {
        status: 404,
      });
    }
    const answer = routes[key];
    // [status, body] when the first item is an HTTP status; a JSON array answer is just a body.
    const tuple = Array.isArray(answer) && answer.length === 2 && typeof answer[0] === "number";
    const [status, body] = tuple ? (answer as [number, unknown]) : [200, answer];
    return new Response(status === 204 ? null : JSON.stringify(body), { status });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export * from "@testing-library/react";
export { userEvent };
