import { apiFetch } from "./client";

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export function registerRequest(email: string, password: string): Promise<User> {
  return apiFetch<User>("/api/v1/auth/register", {
    method: "POST",
    body: { email, password },
    auth: false,
  });
}

export function loginRequest(email: string, password: string): Promise<TokenOut> {
  return apiFetch<TokenOut>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
    auth: false,
  });
}

export function logoutRequest(): Promise<void> {
  return apiFetch<void>("/api/v1/auth/logout", { method: "POST", auth: false });
}

export function fetchMe(): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me");
}
