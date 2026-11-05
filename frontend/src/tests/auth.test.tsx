import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetApiClientState } from "../api/client";
import { apiError, json, mockFetch, noContent } from "./mock-fetch";
import { renderRoute } from "./render-app";

const USER = { id: "u1", email: "me@example.com", created_at: "2026-01-01T00:00:00Z" };
const TOKEN = { access_token: "tok", token_type: "bearer", expires_in: 900 };
const PASSWORD = "correct-horse-battery";

const NO_SESSION = () =>
  apiError(401, "invalid_refresh_token", "Invalid or expired refresh token.");
const SESSION = () => json(200, TOKEN);
const ME = () => json(200, USER);

afterEach(() => {
  vi.unstubAllGlobals();
  resetApiClientState();
});

async function fillAndSubmit(button: string, email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: button }));
}

describe("route guards", () => {
  it("sends a visitor without a session to the login page", async () => {
    mockFetch({ "POST /api/v1/auth/refresh": NO_SESSION });
    await renderRoute("/");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("keeps a returning user signed in", async () => {
    mockFetch({ "POST /api/v1/auth/refresh": SESSION, "GET /api/v1/auth/me": ME });
    await renderRoute("/");
    expect(await screen.findByText("me@example.com")).toBeInTheDocument();
  });

  it("moves a signed-in user away from the login page", async () => {
    mockFetch({ "POST /api/v1/auth/refresh": SESSION, "GET /api/v1/auth/me": ME });
    await renderRoute("/login");
    expect(await screen.findByText("me@example.com")).toBeInTheDocument();
  });

  it("shows the style guide without signing in", async () => {
    mockFetch({ "POST /api/v1/auth/refresh": NO_SESSION });
    await renderRoute("/styleguide");
    expect(screen.getByRole("heading", { name: "Style guide" })).toBeInTheDocument();
  });

  it("shows a page for unknown addresses", async () => {
    mockFetch({ "POST /api/v1/auth/refresh": NO_SESSION });
    await renderRoute("/nope");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});

describe("login", () => {
  it("signs in and shows the dashboard", async () => {
    const { calls } = mockFetch({
      "POST /api/v1/auth/refresh": NO_SESSION,
      "POST /api/v1/auth/login": () => json(200, TOKEN),
      "GET /api/v1/auth/me": ME,
    });
    await renderRoute("/login");
    await screen.findByRole("heading", { name: "Sign in" });

    await fillAndSubmit("Sign in", "me@example.com", PASSWORD);

    expect(await screen.findByText("me@example.com")).toBeInTheDocument();
    const login = calls.find((call) => call.key === "POST /api/v1/auth/login");
    expect(login?.body).toEqual({ email: "me@example.com", password: PASSWORD });
    const me = calls.find((call) => call.key === "GET /api/v1/auth/me");
    expect(me?.headers.Authorization).toBe("Bearer tok");
  });

  it("shows the message from the server when the login is refused", async () => {
    mockFetch({
      "POST /api/v1/auth/refresh": NO_SESSION,
      "POST /api/v1/auth/login": () =>
        apiError(401, "invalid_credentials", "Incorrect email or password."),
    });
    await renderRoute("/login");
    await screen.findByRole("heading", { name: "Sign in" });

    await fillAndSubmit("Sign in", "me@example.com", "wrong-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
  });

  it("checks the form before calling the server", async () => {
    const { calls } = mockFetch({ "POST /api/v1/auth/refresh": NO_SESSION });
    await renderRoute("/login");
    await screen.findByRole("heading", { name: "Sign in" });

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(calls.filter((call) => call.key.includes("/login"))).toHaveLength(0);
  });
});

describe("register", () => {
  it("rejects a short password without calling the server", async () => {
    const { calls } = mockFetch({ "POST /api/v1/auth/refresh": NO_SESSION });
    await renderRoute("/register");
    await screen.findByRole("heading", { name: "Create account" });

    await fillAndSubmit("Create account", "me@example.com", "short");

    expect(screen.getByRole("alert")).toHaveTextContent("Use at least 8 characters.");
    expect(calls.filter((call) => call.key.includes("/register"))).toHaveLength(0);
  });

  it("creates the account, signs in and shows the dashboard", async () => {
    const { calls } = mockFetch({
      "POST /api/v1/auth/refresh": NO_SESSION,
      "POST /api/v1/auth/register": () => json(201, USER),
      "POST /api/v1/auth/login": () => json(200, TOKEN),
      "GET /api/v1/auth/me": ME,
    });
    await renderRoute("/register");
    await screen.findByRole("heading", { name: "Create account" });

    await fillAndSubmit("Create account", "me@example.com", PASSWORD);

    expect(await screen.findByText("me@example.com")).toBeInTheDocument();
    expect(calls.map((call) => call.key)).toEqual([
      "POST /api/v1/auth/refresh",
      "POST /api/v1/auth/register",
      "POST /api/v1/auth/login",
      "GET /api/v1/auth/me",
    ]);
  });

  it("shows a server error such as a taken email", async () => {
    mockFetch({
      "POST /api/v1/auth/refresh": NO_SESSION,
      "POST /api/v1/auth/register": () =>
        apiError(409, "email_taken", "That email is already registered."),
    });
    await renderRoute("/register");
    await screen.findByRole("heading", { name: "Create account" });

    await fillAndSubmit("Create account", "me@example.com", PASSWORD);

    expect(await screen.findByRole("alert")).toHaveTextContent("That email is already registered.");
  });
});

describe("logout", () => {
  it("signs out and returns to the login page", async () => {
    const { calls } = mockFetch({
      "POST /api/v1/auth/refresh": SESSION,
      "GET /api/v1/auth/me": ME,
      "POST /api/v1/auth/logout": noContent,
    });
    await renderRoute("/");
    await screen.findByText("me@example.com");

    await userEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(calls.some((call) => call.key === "POST /api/v1/auth/logout")).toBe(true);
  });
});
