import { describe, expect, it } from "vitest";

import { formatInterval, timeAgo } from "../lib/format";

describe("formatInterval", () => {
  it.each([
    [90, "90 s"],
    [60, "1 min"],
    [300, "5 min"],
    [3600, "1 h"],
    [86400, "24 h"],
  ])("formats %i seconds as %s", (seconds, expected) => {
    expect(formatInterval(seconds)).toBe(expected);
  });
});

describe("timeAgo", () => {
  const now = Date.parse("2026-01-01T12:00:00Z");

  it("says never when there is no date", () => {
    expect(timeAgo(null, now)).toBe("never");
  });

  it.each([
    ["2026-01-01T11:59:55Z", "just now"],
    ["2026-01-01T11:59:30Z", "30 s ago"],
    ["2026-01-01T11:55:00Z", "5 min ago"],
    ["2026-01-01T09:00:00Z", "3 h ago"],
    ["2025-12-30T12:00:00Z", "2 d ago"],
  ])("formats %s as %s", (iso, expected) => {
    expect(timeAgo(iso, now)).toBe(expected);
  });

  it("never shows a negative time for a date slightly in the future", () => {
    expect(timeAgo("2026-01-01T12:00:30Z", now)).toBe("just now");
  });
});
