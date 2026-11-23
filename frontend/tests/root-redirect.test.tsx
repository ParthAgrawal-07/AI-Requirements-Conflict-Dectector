import { afterEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { setAccessToken } from "../src/api/client";
import { RequireAuth, RootRedirect } from "../src/app/routes";
import { mockApi, renderWithProviders, screen } from "./test-utils";

const me = (platformRole: "platform_admin" | null) => ({
  id: "u1",
  email: "parth@acme.in",
  full_name: "Parth Agrawal",
  platform_role: platformRole,
  is_active: true,
  created_at: "2026-10-01T00:00:00Z",
  memberships: [],
});
const TOKEN = { access_token: "jwt", token_type: "bearer", expires_in: 3600 };

function renderRoot() {
  return renderWithProviders(
    <Routes>
      <Route
        path="/"
        element={
          <RequireAuth>
            <RootRedirect />
          </RequireAuth>
        }
      />
      <Route path="/workspaces/new" element={<p>create workspace page</p>} />
      <Route path="/w/:workspaceId" element={<p>workspace page</p>} />
    </Routes>,
    { route: "/", restoreSession: true },
  );
}

afterEach(() => {
  setAccessToken(null);
  vi.unstubAllGlobals();
});

describe("RootRedirect with no workspace", () => {
  it("takes a platform admin straight to creating the first workspace", async () => {
    mockApi({
      "POST /api/v1/auth/refresh": TOKEN,
      "GET /api/v1/auth/me": me("platform_admin"),
      "GET /api/v1/workspaces": [],
    });
    renderRoot();
    expect(await screen.findByText("create workspace page")).toBeInTheDocument();
  });

  it("shows anyone else how to join", async () => {
    mockApi({
      "POST /api/v1/auth/refresh": TOKEN,
      "GET /api/v1/auth/me": me(null),
      "GET /api/v1/workspaces": [],
    });
    renderRoot();
    expect(await screen.findByText("You are not in a workspace yet")).toBeInTheDocument();
    expect(screen.queryByText("create workspace page")).not.toBeInTheDocument();
  });

  it("still opens an existing workspace for a platform admin", async () => {
    mockApi({
      "POST /api/v1/auth/refresh": TOKEN,
      "GET /api/v1/auth/me": me("platform_admin"),
      "GET /api/v1/workspaces": [{ id: "w1", name: "IT314", role: "Owner" }],
    });
    renderRoot();
    expect(await screen.findByText("workspace page")).toBeInTheDocument();
  });
});
