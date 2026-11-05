import { vi } from "vitest";

export interface RecordedRequest {
  key: string; // "METHOD /path"
  headers: Record<string, string>;
  body: unknown;
}

export type Handler = (request: RecordedRequest) => Response | Promise<Response>;

/** Replaces fetch with fakes, one per "METHOD /path". Unknown requests fail the test. */
export function mockFetch(routes: Record<string, Handler>) {
  const calls: RecordedRequest[] = [];
  const fake = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const request: RecordedRequest = {
      key: `${init.method ?? "GET"} ${String(input)}`,
      headers: (init.headers ?? {}) as Record<string, string>,
      body: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
    };
    calls.push(request);
    const handler = routes[request.key];
    if (!handler) throw new Error(`Unexpected request: ${request.key}`);
    return handler(request);
  });
  vi.stubGlobal("fetch", fake);
  return { calls, fetch: fake };
}

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function noContent(): Response {
  return new Response(null, { status: 204 });
}

export function apiError(status: number, code: string, message: string): Response {
  return json(status, { error: { code, message } });
}
