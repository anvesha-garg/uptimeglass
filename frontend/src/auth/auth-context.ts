import { createContext, useContext } from "react";

import type { User } from "../api/auth";

export type AuthStatus = "loading" | "anonymous" | "authenticated";

export interface AuthApi {
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthApi | null>(null);

export function useAuth(): AuthApi {
  const api = useContext(AuthContext);
  if (!api) throw new Error("useAuth must be used inside <AuthProvider>");
  return api;
}
