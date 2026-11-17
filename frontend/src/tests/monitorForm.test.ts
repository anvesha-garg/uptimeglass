import { describe, expect, it } from "vitest";

import { DEFAULT_VALUES, validateForm, valuesFromMonitor } from "../lib/monitorForm";
import type { FormValues } from "../lib/monitorForm";
import { makeMonitor } from "./fixtures";

function values(overrides: Partial<FormValues> = {}): FormValues {
  return { ...DEFAULT_VALUES, name: "My site", url: "https://example.com", ...overrides };
}

describe("validateForm", () => {
  it("accepts the defaults with a name and a URL", () => {
    const { errors, input } = validateForm(values());
    expect(errors).toEqual({});
    expect(input).toEqual({
      name: "My site",
      url: "https://example.com",
      method: "GET",
      interval_seconds: 300,
      timeout_seconds: 10,
      expected_status: 200,
      keyword: null,
    });
  });

  it("trims text and turns a keyword into a value", () => {
    const { input } = validateForm(values({ name: "  Shop ", keyword: " hello " }));
    expect(input?.name).toBe("Shop");
    expect(input?.keyword).toBe("hello");
  });

  it("requires a name and a URL", () => {
    const { errors, input } = validateForm(values({ name: " ", url: "" }));
    expect(errors.name).toBe("Enter a name.");
    expect(errors.url).toBe("Enter a URL.");
    expect(input).toBeNull();
  });

  it.each(["example.com", "ftp://example.com", "javascript:alert(1)"])(
    "refuses the URL %s",
    (url) => {
      expect(validateForm(values({ url })).errors.url).toMatch(/http/);
    },
  );

  it.each(["59", "86401", "abc", "1.5", "", "-60"])("refuses the interval %j", (interval) => {
    expect(validateForm(values({ interval })).errors.interval).toBeDefined();
  });

  it("requires the timeout to be below the interval", () => {
    const { errors } = validateForm(values({ interval: "60", timeout: "60" }));
    expect(errors.timeout).toBe("Must be less than the check interval.");
  });

  it.each(["0", "61", "x"])("refuses the timeout %j", (timeout) => {
    expect(validateForm(values({ timeout })).errors.timeout).toBeDefined();
  });

  it.each(["99", "600", ""])("refuses the expected status %j", (expectedStatus) => {
    expect(validateForm(values({ expectedStatus })).errors.expectedStatus).toBeDefined();
  });

  it("refuses a keyword together with HEAD", () => {
    const { errors } = validateForm(values({ method: "HEAD", keyword: "hello" }));
    expect(errors.keyword).toBe("Keyword checks need the GET method.");
    expect(validateForm(values({ method: "HEAD" })).errors).toEqual({});
  });
});

describe("valuesFromMonitor", () => {
  it("turns a monitor into form values", () => {
    const monitor = makeMonitor({ interval_seconds: 120, keyword: "ok" });
    expect(valuesFromMonitor(monitor)).toEqual({
      name: "Site A",
      url: "https://example.com",
      method: "GET",
      interval: "120",
      timeout: "10",
      expectedStatus: "200",
      keyword: "ok",
    });
  });

  it("uses an empty text for a missing keyword", () => {
    expect(valuesFromMonitor(makeMonitor()).keyword).toBe("");
  });
});
