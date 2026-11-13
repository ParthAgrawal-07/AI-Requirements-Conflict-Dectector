// Authentication state (Pranshu — US-19).
//
// The JWT is kept in memory only (US-19 AC; never localStorage, so an XSS bug cannot read a
// stored token). Silent re-login rests on the HttpOnly refresh cookie the backend sets at sign-in:
// on page load the provider restores the session from it, and apiFetch refreshes an expired
// token and retries (api/client.ts). Only when the cookie is gone too (expired, revoked, signed
// out elsewhere) is the session cleared and the user sent to the sign-in screen, which returns
// them to where they were afterwards.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  apiFetch,
  refreshAccessToken,
  setAccessToken,
  setUnauthorizedHandler,
} from "../api/client";
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
  /** True while a page load tries to restore the session from the refresh cookie. */
  restoring: boolean;
  /** Set when the session ended because the token expired (shown on the sign-in screen). */
  expired: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (input: SignupInput) => Promise<SignupResponse>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

interface AuthProviderProps {
  children: ReactNode;
  /** Try the refresh cookie on mount. Tests turn it off unless they are about it. */
  restoreSession?: boolean;
}

export function AuthProvider({ children, restoreSession = true }: AuthProviderProps) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(restoreSession);
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(false);
  const [expired, setExpired] = useState(false);

  const start = useCallback(async (newToken: string) => {
    setAccessToken(newToken);
    setExpired(false);
    setLoading(true);
    try {
      const me = await apiFetch<Me>("/auth/me");
      setUser(me);
      setToken(newToken);
    } catch (error) {
      setAccessToken(null);
      setToken(null);
      setUser(null);
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    // Revoke the refresh cookie server-side. Best effort: sign-out is immediate either way.
    apiFetch("/auth/logout", { method: "POST" }).catch(() => undefined);
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

  useEffect(() => {
    if (!restoreSession) return;
    let cancelled = false;
    void (async () => {
      const restored = await refreshAccessToken();
      if (restored && !cancelled) {
        await start(restored).catch(() => undefined); // no session: the sign-in screen shows
      }
      if (!cancelled) setRestoring(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [restoreSession, start]);

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
    () => ({ token, user, loading, restoring, expired, login, signup, logout, refreshUser }),
    [token, user, loading, restoring, expired, login, signup, logout, refreshUser],
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
