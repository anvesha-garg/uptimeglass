import type { Monitor, MonitorInput } from "../api/monitors";

/** Form fields are strings, because that is what inputs hold. */
export interface FormValues {
  name: string;
  url: string;
  method: "GET" | "HEAD";
  interval: string;
  timeout: string;
  expectedStatus: string;
  keyword: string;
}

export type FormErrors = Partial<Record<keyof FormValues, string>>;

export const DEFAULT_VALUES: FormValues = {
  name: "",
  url: "",
  method: "GET",
  interval: "300",
  timeout: "10",
  expectedStatus: "200",
  keyword: "",
};

export function valuesFromMonitor(monitor: Monitor): FormValues {
  return {
    name: monitor.name,
    url: monitor.url,
    method: monitor.method,
    interval: String(monitor.interval_seconds),
    timeout: String(monitor.timeout_seconds),
    expectedStatus: String(monitor.expected_status),
    keyword: monitor.keyword ?? "",
  };
}

function parseInteger(text: string): number | null {
  const trimmed = text.trim();
  return /^\d+$/.test(trimmed) ? Number(trimmed) : null;
}

/**
 * Checks the form the same way the backend does, so mistakes show up at once.
 * The backend still checks everything again: this is only for convenience.
 */
export function validateForm(values: FormValues): {
  errors: FormErrors;
  input: MonitorInput | null;
} {
  const errors: FormErrors = {};
  const name = values.name.trim();
  const url = values.url.trim();
  const keyword = values.keyword.trim();

  if (!name) errors.name = "Enter a name.";
  else if (name.length > 100) errors.name = "Use at most 100 characters.";

  if (!url) errors.url = "Enter a URL.";
  else if (!/^https?:\/\//i.test(url)) errors.url = "The URL must start with http:// or https://.";
  else if (url.length > 2048) errors.url = "The URL is too long.";

  const interval = parseInteger(values.interval);
  if (interval === null || interval < 60 || interval > 86400) {
    errors.interval = "Enter 60 to 86400 seconds.";
  }

  const timeout = parseInteger(values.timeout);
  if (timeout === null || timeout < 1 || timeout > 60) {
    errors.timeout = "Enter 1 to 60 seconds.";
  } else if (interval !== null && !errors.interval && timeout >= interval) {
    errors.timeout = "Must be less than the check interval.";
  }

  const expectedStatus = parseInteger(values.expectedStatus);
  if (expectedStatus === null || expectedStatus < 100 || expectedStatus > 599) {
    errors.expectedStatus = "Enter a status from 100 to 599.";
  }

  if (keyword.length > 200) errors.keyword = "Use at most 200 characters.";
  else if (values.method === "HEAD" && keyword) {
    errors.keyword = "Keyword checks need the GET method.";
  }

  if (
    Object.keys(errors).length > 0 ||
    interval === null ||
    timeout === null ||
    expectedStatus === null
  ) {
    return { errors, input: null };
  }

  return {
    errors,
    input: {
      name,
      url,
      method: values.method,
      interval_seconds: interval,
      timeout_seconds: timeout,
      expected_status: expectedStatus,
      keyword: keyword || null,
    },
  };
}
