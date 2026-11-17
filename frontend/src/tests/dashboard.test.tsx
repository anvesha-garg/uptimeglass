import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetApiClientState } from "../api/client";
import { AUTH_ROUTES, makeMonitor, monitorPage } from "./fixtures";
import { json, mockFetch } from "./mock-fetch";
import { renderRoute } from "./render-app";

const LIST = "GET /api/v1/monitors?limit=100";
const OPEN_INCIDENTS = "GET /api/v1/incidents?status=open&limit=1";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetApiClientState();
});

describe("Dashboard", () => {
  it("counts the monitors by status and the open incidents", async () => {
    mockFetch({
      ...AUTH_ROUTES,
      [LIST]: () =>
        json(
          200,
          monitorPage([
            makeMonitor({ id: "a", name: "Alpha", status: "UP" }),
            makeMonitor({ id: "b", name: "Beta", status: "DEGRADED" }),
            makeMonitor({ id: "c", name: "Gamma", status: "DOWN" }),
            makeMonitor({ id: "d", name: "Delta", status: "PAUSED", is_paused: true }),
          ]),
        ),
      [OPEN_INCIDENTS]: () => json(200, { items: [], total: 2, limit: 1, offset: 0 }),
    });
    await renderRoute("/");

    const stat = (id: string) => within(screen.getByTestId(`stat-${id}`));
    await waitFor(() => expect(stat("total").getByText("4")).toBeInTheDocument());
    expect(stat("up").getByText("1")).toBeInTheDocument();
    expect(stat("degraded").getByText("1")).toBeInTheDocument();
    expect(stat("down").getByText("1")).toBeInTheDocument();
    await waitFor(() => expect(stat("incidents").getByText("2")).toBeInTheDocument());
  });

  it("lists only the monitors that need attention", async () => {
    mockFetch({
      ...AUTH_ROUTES,
      [LIST]: () =>
        json(
          200,
          monitorPage([
            makeMonitor({ id: "a", name: "Alpha", status: "UP" }),
            makeMonitor({ id: "b", name: "Beta", status: "DEGRADED" }),
            makeMonitor({ id: "c", name: "Gamma", status: "DOWN" }),
          ]),
        ),
    });
    await renderRoute("/");

    expect(await screen.findByText("Gamma")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
  });

  it("says so when everything is healthy", async () => {
    mockFetch({
      ...AUTH_ROUTES,
      [LIST]: () => json(200, monitorPage([makeMonitor({ status: "UP" })])),
    });
    await renderRoute("/");
    expect(await screen.findByText("All monitors are healthy.")).toBeInTheDocument();
  });

  it("invites the user to add a first monitor", async () => {
    mockFetch({ ...AUTH_ROUTES });
    await renderRoute("/");
    expect(await screen.findByRole("heading", { name: "No monitors yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add your first monitor" })).toHaveAttribute(
      "href",
      "/monitors",
    );
  });
});

describe("App shell", () => {
  it("shows the email, the navigation, and moves between pages", async () => {
    mockFetch({ ...AUTH_ROUTES });
    const user = userEvent.setup();
    await renderRoute("/");

    expect(await screen.findByText("me@example.com")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    await user.click(within(nav).getByRole("link", { name: "Monitors" }));
    expect(await screen.findByRole("heading", { name: "Monitors" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Monitors" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("switches the theme", async () => {
    mockFetch({ ...AUTH_ROUTES });
    const user = userEvent.setup();
    await renderRoute("/");

    await user.click(await screen.findByRole("button", { name: /switch to light theme/i }));
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
