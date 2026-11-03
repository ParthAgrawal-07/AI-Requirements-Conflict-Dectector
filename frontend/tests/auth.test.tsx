import { afterEach, describe, expect, it, vi } from "vitest";
import { getAccessToken, setAccessToken } from "../src/api/client";
import { LoginPage } from "../src/features/auth/LoginPage";
import { SignupWithCodePage } from "../src/features/auth/SignupWithCodePage";
import { mockApi, renderWithProviders, screen, waitFor } from "./test-utils";

const ME = {
  id: "u1",
  email: "riya@acme.in",
  full_name: "Riya Kumar",
  platform_role: null,
  is_active: true,
  created_at: "2026-10-01T00:00:00Z",
  memberships: [],
};

afterEach(() => {
  setAccessToken(null);
  vi.unstubAllGlobals();
});

describe("LoginPage", () => {
  it("signs in with the OAuth2 form and keeps the token in memory only", async () => {
    const { calls } = mockApi({
      "POST /api/v1/auth/login": { access_token: "jwt", token_type: "bearer", expires_in: 3600 },
      "GET /api/v1/auth/me": ME,
    });
    const storage = vi.spyOn(Storage.prototype, "setItem");
    const { user } = renderWithProviders(<LoginPage />, { route: "/login", path: "/login" });

    await user.type(screen.getByLabelText("Work email"), "riya@acme.in");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByText("navigated away")).toBeInTheDocument());
    expect(String(calls[0].body)).toBe("username=riya%40acme.in&password=correct-horse-battery");
    expect(getAccessToken()).toBe("jwt");
    expect(storage).not.toHaveBeenCalledWith(expect.anything(), expect.stringContaining("jwt"));
  });

  it("shows the server's generic message on bad credentials", async () => {
    mockApi({
      "POST /api/v1/auth/login": [
        401,
        { error: { code: "invalid_credentials", message: "Incorrect email or password" } },
      ],
    });
    const { user } = renderWithProviders(<LoginPage />, { route: "/login", path: "/login" });

    await user.type(screen.getByLabelText("Work email"), "x@y.z");
    await user.type(screen.getByLabelText("Password"), "nope");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
  });
});

describe("SignupWithCodePage", () => {
  it("prefills the code from a join link", () => {
    renderWithProviders(<SignupWithCodePage />, {
      route: "/signup?code=K7QM-4XPA",
      path: "/signup",
    });
    expect(screen.getByLabelText("Join code")).toHaveValue("K7QM-4XPA");
  });

  it("creates the account and opens the joined workspace", async () => {
    const { calls } = mockApi({
      "POST /api/v1/auth/signup": {
        access_token: "jwt",
        token_type: "bearer",
        expires_in: 3600,
        user: ME,
        join_status: "joined",
        workspace_id: "w1",
      },
      "GET /api/v1/auth/me": ME,
    });
    const { user } = renderWithProviders(<SignupWithCodePage />, {
      route: "/signup",
      path: "/signup",
    });

    await user.type(screen.getByLabelText("Join code"), " k7qm-4xpa ");
    await user.type(screen.getByLabelText("Full name"), "Riya Kumar");
    await user.type(screen.getByLabelText("Work email"), "riya@acme.in");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(screen.getByText("navigated away")).toBeInTheDocument());
    expect(JSON.parse(String(calls[0].body))).toMatchObject({ code: "k7qm-4xpa" });
  });

  it("explains a pending approval instead of opening a workspace", async () => {
    mockApi({
      "POST /api/v1/auth/signup": {
        access_token: "jwt",
        token_type: "bearer",
        expires_in: 3600,
        user: ME,
        join_status: "pending_approval",
        workspace_id: null,
      },
      "GET /api/v1/auth/me": ME,
    });
    const { user } = renderWithProviders(<SignupWithCodePage />, {
      route: "/signup",
      path: "/signup",
    });
    await user.type(screen.getByLabelText("Join code"), "K7QM-4XPA");
    await user.type(screen.getByLabelText("Full name"), "N");
    await user.type(screen.getByLabelText("Work email"), "n@acme.in");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/approve your request/i)).toBeInTheDocument();
  });

  it("shows the one refusal message for a bad code", async () => {
    mockApi({
      "POST /api/v1/auth/signup": [
        400,
        { error: { code: "signup_refused", message: "We could not create an account." } },
      ],
    });
    const { user } = renderWithProviders(<SignupWithCodePage />, {
      route: "/signup",
      path: "/signup",
    });
    await user.type(screen.getByLabelText("Join code"), "ZZZZ-ZZZZ");
    await user.type(screen.getByLabelText("Full name"), "N");
    await user.type(screen.getByLabelText("Work email"), "n@acme.in");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("We could not create an account.");
  });
});
