import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetApiClientState } from "../api/client";
import { THEME_STORAGE_KEY } from "../hooks/useTheme";
import { apiError, mockFetch } from "./mock-fetch";
import { renderRoute } from "./render-app";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  mockFetch({
    "POST /api/v1/auth/refresh": () =>
      apiError(401, "invalid_refresh_token", "Invalid or expired refresh token."),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetApiClientState();
});

describe("Style guide page", () => {
  it("shows the style guide with its sections", async () => {
    await renderRoute("/styleguide");
    expect(screen.getByRole("heading", { name: "Style guide" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Buttons" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Status badges" })).toBeInTheDocument();
  });

  it("starts in the dark theme", async () => {
    await renderRoute("/styleguide");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("switches to light, and remembers it", async () => {
    const user = userEvent.setup();
    await renderRoute("/styleguide");

    await user.click(screen.getByRole("button", { name: /switch to light theme/i }));

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(screen.getByRole("button", { name: /switch to dark theme/i })).toBeInTheDocument();
  });

  it("restores a saved light theme", async () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    await renderRoute("/styleguide");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("ignores a broken saved value", async () => {
    localStorage.setItem(THEME_STORAGE_KEY, "purple");
    await renderRoute("/styleguide");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
