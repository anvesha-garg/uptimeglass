import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, getAccessToken, resetApiClientState, setAccessToken, setUnauthorizedHandler } from "../api/client";
import { apiError, json, mockFetch, noContent } from "./mock-fetch";

const USER = { id: "u1", email: "me@example.com", created_at: "2026-01-01T00:00:00Z" };
const NEW_TOKEN = { access_token: "new", token_type: "bearer", expires_in: 900 };
const EXPIRED = () => apiError(401, "invalid_token", "Invalid or expired access token.");

afterEach(() => {
  vi.unstubAllGlobals();
  resetApiClientState();
});

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    return error as ApiError;
  }
  throw new Error("Expected the request to fail");
}

describe("apiFetch", () => {
  it("sends the access token as a bearer header", async () => {
    setAccessToken("abc");
    const { calls } = mockFetch({ "GET /api/v1/auth/me": () => json(200, USER) });

    expect(await apiFetch("/api/v1/auth/me")).toEqual(USER);
    expect(calls[0].headers.Authorization).toBe("Bearer abc");
  });

  it("reads the standard error format", async () => {
    mockFetch({
      "POST /api/v1/auth/register": () => apiError(409, "email_taken", "That email is already registered."),
    });
    const error = await failure(
      apiFetch("/api/v1/auth/register", { method: "POST", body: {}, auth: false }),
    );
    expect(error).toBeInstanceOf(ApiError);
    expect([error.status, error.code, error.message]).toEqual([
      409,
      "email_taken",
      "That email is already registered.",
    ]);
  });

  it("falls back to a generic error when the body is not JSON", async () => {
    mockFetch({ "GET /api/v1/x": () => new Response("<html>Bad gateway</html>", { status: 502 }) });
    const error = await failure(apiFetch("/api/v1/x"));
    expect([error.status, error.code]).toEqual([502, "http_error"]);
  });

  it("returns nothing for a 204 response", async () => {
    mockFetch({ "POST /api/v1/auth/logout": noContent });
    expect(await apiFetch("/api/v1/auth/logout", { method: "POST", auth: false })).toBeUndefined();
  });

  it("turns an unreachable server into a network error", async () => {
    mockFetch({
      "GET /api/v1/x": () => {
        throw new TypeError("Failed to fetch");
      },
    });
    const error = await failure(apiFetch("/api/v1/x", { auth: false }));
    expect([error.status, error.code]).toEqual([0, "network_error"]);
  });

  it("refreshes an expired token and retries the request once", async () => {
    setAccessToken("old");
    const { calls } = mockFetch({
      "GET /api/v1/auth/me": ({ headers }) =>
        headers.Authorization === "Bearer new" ? json(200, USER) : EXPIRED(),
      "POST /api/v1/auth/refresh": () => json(200, NEW_TOKEN),
    });

    expect(await apiFetch("/api/v1/auth/me")).toEqual(USER);
    expect(calls.map((call) => call.key)).toEqual([
      "GET /api/v1/auth/me",
      "POST /api/v1/auth/refresh",
      "GET /api/v1/auth/me",
    ]);
    expect(getAccessToken()).toBe("new");
  });

  it("shares ONE refresh between requests that fail at the same time", async () => {
    setAccessToken("old");
    const { calls } = mockFetch({
      "GET /api/v1/auth/me": ({ headers }) =>
        headers.Authorization === "Bearer new" ? json(200, USER) : EXPIRED(),
      "POST /api/v1/auth/refresh": async () => {
        await new Promise((resolve) => setTimeout(resolve, 20)); // slow enough to overlap
        return json(200, NEW_TOKEN);
      },
    });

    const results = await Promise.all([
      apiFetch("/api/v1/auth/me"),
      apiFetch("/api/v1/auth/me"),
      apiFetch("/api/v1/auth/me"),
    ]);

    expect(results).toEqual([USER, USER, USER]);
    expect(calls.filter((call) => call.key === "POST /api/v1/auth/refresh")).toHaveLength(1);
  });

  it("signs out when the session cannot be renewed", async () => {
    setAccessToken("old");
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    mockFetch({
      "GET /api/v1/auth/me": EXPIRED,
      "POST /api/v1/auth/refresh": () =>
        apiError(401, "invalid_refresh_token", "Invalid or expired refresh token."),
    });

    const error = await failure(apiFetch("/api/v1/auth/me"));
    expect(error.status).toBe(401);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
  });

  it("does not try to refresh when a login is refused", async () => {
    const { calls } = mockFetch({
      "POST /api/v1/auth/login": () =>
        apiError(401, "invalid_credentials", "Incorrect email or password."),
    });
    const error = await failure(
      apiFetch("/api/v1/auth/login", { method: "POST", body: {}, auth: false }),
    );
    expect(error.code).toBe("invalid_credentials");
    expect(calls).toHaveLength(1);
  });
});
