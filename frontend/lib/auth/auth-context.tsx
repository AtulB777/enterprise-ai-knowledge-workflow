"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiFetch, setAccessToken } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/client";

type TokenResponse = Schemas["TokenResponse"];
type UserResponse = Schemas["UserResponse"];

const REFRESH_TOKEN_KEY = "eaikp_refresh_token";

interface AuthContextValue {
  user: UserResponse | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    fullName: string,
    organizationName: string,
  ) => Promise<void>;
  logout: () => Promise<void>;
  refetchUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchCurrentUser(): Promise<UserResponse> {
  return apiFetch<UserResponse>("/api/v1/users/me");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const applyTokens = useCallback((tokens: TokenResponse) => {
    setAccessToken(tokens.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    setUser(null);
  }, []);

  // On first load, try to resume a session from the persisted refresh
  // token — this is what makes a page reload not force a re-login (see
  // ADR-015 decision 4 for the storage trade-off this implies).
  useEffect(() => {
    async function resumeSession() {
      const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (!storedRefreshToken) {
        setIsLoading(false);
        return;
      }
      try {
        const tokens = await apiFetch<TokenResponse>("/api/v1/auth/refresh", {
          method: "POST",
          body: { refresh_token: storedRefreshToken },
          skipAuth: true,
        });
        applyTokens(tokens);
        const currentUser = await fetchCurrentUser();
        setUser(currentUser);
      } catch {
        clearSession();
      } finally {
        setIsLoading(false);
      }
    }
    void resumeSession();
  }, [applyTokens, clearSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await apiFetch<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        body: { email, password },
        skipAuth: true,
      });
      applyTokens(tokens);
      const currentUser = await fetchCurrentUser();
      setUser(currentUser);
    },
    [applyTokens],
  );

  const register = useCallback(
    async (email: string, password: string, fullName: string, organizationName: string) => {
      const tokens = await apiFetch<TokenResponse>("/api/v1/auth/register", {
        method: "POST",
        body: {
          email,
          password,
          full_name: fullName,
          organization_name: organizationName,
        },
        skipAuth: true,
      });
      applyTokens(tokens);
      const currentUser = await fetchCurrentUser();
      setUser(currentUser);
    },
    [applyTokens],
  );

  const logout = useCallback(async () => {
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (storedRefreshToken) {
      try {
        await apiFetch("/api/v1/auth/logout", {
          method: "POST",
          body: { refresh_token: storedRefreshToken },
        });
      } catch {
        // Logging out client-side should succeed regardless of whether the
        // server-side token revocation call itself succeeded — the user's
        // intent (end this session, here, now) is what matters locally.
      }
    }
    clearSession();
  }, [clearSession]);

  const refetchUser = useCallback(async () => {
    const currentUser = await fetchCurrentUser();
    setUser(currentUser);
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, login, register, logout, refetchUser }),
    [user, isLoading, login, register, logout, refetchUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
