import type { Monitor } from "../api/monitors";
import { json } from "./mock-fetch";
import type { Handler } from "./mock-fetch";

export const USER = { id: "u1", email: "me@example.com", created_at: "2026-01-01T00:00:00Z" };
export const TOKEN = { access_token: "tok", token_type: "bearer", expires_in: 900 };

/** A signed-in visitor: the silent refresh works and /auth/me answers. */
export const AUTH_ROUTES: Record<string, Handler> = {
  "POST /api/v1/auth/refresh": () => json(200, TOKEN),
  "GET /api/v1/auth/me": () => json(200, USER),
};

export function makeMonitor(overrides: Partial<Monitor> = {}): Monitor {
  return {
    id: "m1",
    name: "Site A",
    url: "https://example.com",
    method: "GET",
    interval_seconds: 300,
    timeout_seconds: 10,
    expected_status: 200,
    keyword: null,
    is_paused: false,
    status: "UP",
    consecutive_failures: 0,
    consecutive_successes: 0,
    consecutive_slow: 0,
    next_check_at: "2026-01-01T00:05:00Z",
    last_checked_at: "2026-01-01T00:00:00Z",
    ssl_expires_at: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

export function monitorPage(items: Monitor[]) {
  return { items, total: items.length, limit: 100, offset: 0 };
}
