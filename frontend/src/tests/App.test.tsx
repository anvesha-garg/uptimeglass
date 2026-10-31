import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import App from "../App";
import { THEME_STORAGE_KEY } from "../hooks/useTheme";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("App", () => {
  it("shows the title and the glass card", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "UptimeGlass" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /liquid glass surface/i })).toBeInTheDocument();
  });

  it("starts in the dark theme", () => {
    render(<App />);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("switches to light, and remembers it", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /switch to light theme/i }));

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(screen.getByRole("button", { name: /switch to dark theme/i })).toBeInTheDocument();
  });

  it("restores a saved light theme", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    render(<App />);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("ignores a broken saved value", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "purple");
    render(<App />);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
