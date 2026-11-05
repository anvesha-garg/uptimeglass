import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { fetchMe, loginRequest, logoutRequest, registerRequest } from "../api/auth";
import type { User } from "../api/auth";
import { refreshAccessToken, setAccessToken, setUnauthorizedHandler } from "../api/client";
import { AuthContext } from "./auth-context";
import type { AuthStatus } from "./auth-context";

interface AuthState {
  status: AuthStatus;
  user: User | null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  // The API client calls this when a session cannot be renewed any more.
  useEffect(() => {
    setUnauthorizedHandler(() => setState({ status: "anonymous", user: null }));
    return () => setUnauthorizedHandler(null);
  }, []);

  // On page load, try to continue the session with the refresh cookie.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refreshAccessToken();
        const user = await fetchMe();
        if (!cancelled) setState({ status: "authenticated", user });
      } catch {
        if (!cancelled) setState({ status: "anonymous", user: null });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const token = await loginRequest(email, password);
    setAccessToken(token.access_token);
    const user = await fetchMe();
    setState({ status: "authenticated", user });
  }, []);

  const register = useCallback(
    async (email: string, password: string) => {
      await registerRequest(email, password);
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } catch {
      // The cookie may already be gone. We sign out in this browser either way.
    }
    setAccessToken(null);
    queryClient.clear(); // no data from this user stays in memory
    setState({ status: "anonymous", user: null });
  }, [queryClient]);

  const value = useMemo(
    () => ({ ...state, login, register, logout }),
    [state, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
