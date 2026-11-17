import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetApiClientState } from "../api/client";
import type { Monitor, MonitorInput } from "../api/monitors";
import { AUTH_ROUTES, makeMonitor, monitorPage } from "./fixtures";
import { apiError, json, mockFetch, noContent } from "./mock-fetch";
import { renderRoute } from "./render-app";

const LIST = "GET /api/v1/monitors?limit=100";

afterEach(() => {
  vi.unstubAllGlobals();
  resetApiClientState();
});

describe("Monitors page", () => {
  it("lists the monitors with their status", async () => {
    mockFetch({
      ...AUTH_ROUTES,
      [LIST]: () =>
        json(
          200,
          monitorPage([
            makeMonitor({ id: "a", name: "Alpha", status: "UP" }),
            makeMonitor({ id: "b", name: "Beta", status: "DOWN" }),
          ]),
        ),
    });
    await renderRoute("/monitors");

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Down")).toBeInTheDocument();
    expect(screen.getByText("2 of 20 monitors")).toBeInTheDocument();
  });

  it("shows an empty state with a way to add the first monitor", async () => {
    mockFetch({ ...AUTH_ROUTES });
    await renderRoute("/monitors");

    expect(await screen.findByRole("heading", { name: "No monitors yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add your first monitor" })).toBeInTheDocument();
  });

  it("shows an error and loads again when asked", async () => {
    let attempts = 0;
    mockFetch({
      ...AUTH_ROUTES,
      [LIST]: () => {
        attempts += 1;
        return attempts === 1
          ? apiError(500, "internal_error", "Something went wrong on our side.")
          : json(200, monitorPage([makeMonitor({ name: "Alpha" })]));
      },
    });
    await renderRoute("/monitors");

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
  });

  it("creates a monitor from the form", async () => {
    const list: Monitor[] = [];
    const { calls } = mockFetch({
      ...AUTH_ROUTES,
      [LIST]: () => json(200, monitorPage(list)),
      "POST /api/v1/monitors": ({ body }) => {
        const input = body as MonitorInput;
        const created = makeMonitor({ id: "new", name: input.name, url: input.url });
        list.push(created);
        return json(201, created);
      },
    });
    const user = userEvent.setup();
    await renderRoute("/monitors");

    await user.click(await screen.findByRole("button", { name: "Add monitor" }));
    await user.type(screen.getByLabelText("Name"), "My site");
    await user.type(screen.getByLabelText("URL"), "https://example.com");
    await user.click(screen.getByRole("button", { name: "Create monitor" }));

    expect(await screen.findByText("My site")).toBeInTheDocument();
    const post = calls.find((call) => call.key === "POST /api/v1/monitors");
    expect(post?.body).toEqual({
      name: "My site",
      url: "https://example.com",
      method: "GET",
      interval_seconds: 300,
      timeout_seconds: 10,
      expected_status: 200,
      keyword: null,
    });
  });

  it("checks the form before calling the server", async () => {
    const { calls } = mockFetch({ ...AUTH_ROUTES });
    const user = userEvent.setup();
    await renderRoute("/monitors");

    await user.click(await screen.findByRole("button", { name: "Add monitor" }));
    await user.click(screen.getByRole("button", { name: "Create monitor" }));

    expect(screen.getByText("Enter a name.")).toBeInTheDocument();
    expect(screen.getByText("Enter a URL.")).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith("POST /api/v1/monitors"))).toBe(false);
  });

  it("shows a refused address next to the URL field", async () => {
    mockFetch({
      ...AUTH_ROUTES,
      "POST /api/v1/monitors": () =>
        apiError(422, "invalid_url", "The URL points to a private or internal address."),
    });
    const user = userEvent.setup();
    await renderRoute("/monitors");

    await user.click(await screen.findByRole("button", { name: "Add monitor" }));
    await user.type(screen.getByLabelText("Name"), "Local");
    await user.type(screen.getByLabelText("URL"), "http://127.0.0.1");
    await user.click(screen.getByRole("button", { name: "Create monitor" }));

    expect(
      await screen.findByText("The URL points to a private or internal address."),
    ).toBeInTheDocument();
  });

  it("edits a monitor, starting from its current values", async () => {
    const monitor = makeMonitor({ name: "Site A" });
    const { calls } = mockFetch({
      ...AUTH_ROUTES,
      [LIST]: () => json(200, monitorPage([monitor])),
      "PATCH /api/v1/monitors/m1": ({ body }) => {
        monitor.name = (body as MonitorInput).name;
        return json(200, monitor);
      },
    });
    const user = userEvent.setup();
    await renderRoute("/monitors");

    await user.click(await screen.findByRole("button", { name: "Edit Site A" }));
    const name = screen.getByLabelText("Name");
    expect(name).toHaveValue("Site A");
    await user.clear(name);
    await user.type(name, "Renamed");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Renamed")).toBeInTheDocument();
    const patch = calls.find((call) => call.key === "PATCH /api/v1/monitors/m1");
    expect((patch?.body as MonitorInput).name).toBe("Renamed");
  });

  it("pauses and resumes a monitor", async () => {
    const monitor = makeMonitor();
    mockFetch({
      ...AUTH_ROUTES,
      [LIST]: () => json(200, monitorPage([monitor])),
      "POST /api/v1/monitors/m1/pause": () => {
        monitor.is_paused = true;
        monitor.status = "PAUSED";
        return json(200, monitor);
      },
    });
    const user = userEvent.setup();
    await renderRoute("/monitors");

    await user.click(await screen.findByRole("button", { name: "Pause Site A" }));
    expect(await screen.findByRole("button", { name: "Resume Site A" })).toBeInTheDocument();
    expect(screen.getByText("Paused")).toBeInTheDocument();
  });

  it("asks before deleting, then removes the monitor", async () => {
    const list = [makeMonitor()];
    const { calls } = mockFetch({
      ...AUTH_ROUTES,
      [LIST]: () => json(200, monitorPage(list)),
      "DELETE /api/v1/monitors/m1": () => {
        list.length = 0;
        return noContent();
      },
    });
    const user = userEvent.setup();
    await renderRoute("/monitors");

    await user.click(await screen.findByRole("button", { name: "Delete Site A" }));
    expect(screen.getByRole("dialog", { name: "Delete monitor?" })).toBeInTheDocument();
    expect(calls.some((call) => call.key.startsWith("DELETE"))).toBe(false); // not yet

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("heading", { name: "No monitors yet" })).toBeInTheDocument();
    expect(calls.some((call) => call.key === "DELETE /api/v1/monitors/m1")).toBe(true);
  });
});
