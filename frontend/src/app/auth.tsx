// Authentication state (Pranshu — US-19).
//
// The JWT is kept in memory only (US-19 AC; never localStorage, so an XSS bug cannot read a
// stored token). Reloading the tab therefore asks the user to sign in again. When the server
// answers 401 the session is cleared and the user is sent to the sign-in screen, which returns
// them to where they were afterwards. Silent re-login needs a refresh endpoint on the backend
// (Parth) — until it exists, an expired token means signing in again.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiFetch, setAccessToken, setUnauthorizedHandler } from "../api/client";
import type { Me, SignupResponse, TokenResponse } from "../api/types";

export interface SignupInput {
  email: string;
  password: string;
  full_name: string;
  code: string;
}

interface AuthState {
  token: string | null;
  user: Me | null;
  /** True between a successful token and the first /auth/me answer. */
  loading: boolean;
  /** Set when the session ended because the token expired (shown on the sign-in screen). */
  expired: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (input: SignupInput) => Promise<SignupResponse>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(false);
  const [expired, setExpired] = useState(false);

  const start = useCallback(async (newToken: string) => {
    setAccessToken(newToken);
    setToken(newToken);
    setExpired(false);
    setLoading(true);
    try {
      setUser(await apiFetch<Me>("/auth/me"));
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    setAccessToken(null);
    setToken(null);
    setUser(null);
    queryClient.clear(); // nothing of the previous user's data survives sign-out
  }, [queryClient]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      logout();
      setExpired(true);
    });
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = useCallback(
    async (email: string, password: string) => {
      // OAuth2 password form (backend app/api/auth.py): username + password, urlencoded.
      const form = new URLSearchParams({ username: email, password });
      const response = await apiFetch<TokenResponse>("/auth/login", { method: "POST", form });
      await start(response.access_token);
    },
    [start],
  );

  const signup = useCallback(
    async (input: SignupInput) => {
      const response = await apiFetch<SignupResponse>("/auth/signup", {
        method: "POST",
        json: input,
      });
      await start(response.access_token);
      return response;
    },
    [start],
  );

  const refreshUser = useCallback(async () => {
    setUser(await apiFetch<Me>("/auth/me"));
  }, []);

  const value = useMemo<AuthState>(
    () => ({ token, user, loading, expired, login, signup, logout, refreshUser }),
    [token, user, loading, expired, login, signup, logout, refreshUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
