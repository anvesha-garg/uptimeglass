/** The fetch wrapper for the backend API. The access token lives here, in memory only. */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

let accessToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;
let refreshPromise: Promise<string> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Called when the session cannot be renewed any more, so the app can show the login page. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

/** For tests: forget everything this module remembers. */
export function resetApiClientState(): void {
  accessToken = null;
  unauthorizedHandler = null;
  refreshPromise = null;
}

/** Turns an error response into an ApiError, using the backend's standard error format. */
async function toApiError(response: Response): Promise<ApiError> {
  try {
    const data = await response.json();
    const error = data?.error;
    if (error && typeof error.code === "string" && typeof error.message === "string") {
      return new ApiError(response.status, error.code, error.message);
    }
  } catch {
    // Not JSON (for example a proxy error page): use the generic message below.
  }
  return new ApiError(response.status, "http_error", `The request failed (${response.status}).`);
}

async function send(
  path: string,
  method: string,
  body: unknown,
  token: string | null,
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    return await fetch(path, {
      method,
      headers,
      credentials: "same-origin", // sends the httpOnly refresh cookie to our own origin
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    // fetch throws a TypeError when the server cannot be reached at all.
    if (error instanceof TypeError) {
      throw new ApiError(0, "network_error", "Could not reach the server. Check your connection.");
    }
    throw error;
  }
}

/**
 * Gets a new access token with the refresh cookie. Calls made while a refresh is already
 * running share it. The backend rotates refresh tokens and treats a reused one as theft,
 * so two parallel refreshes would sign the user out.
 */
export function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const response = await send("/api/v1/auth/refresh", "POST", undefined, null);
      if (!response.ok) throw await toApiError(response);
      const data = (await response.json()) as { access_token: string };
      accessToken = data.access_token;
      return data.access_token;
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** false for login and register: a 401 there is an answer, not an expired token. */
  auth?: boolean;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true } = options;

  let response = await send(path, method, body, auth ? accessToken : null);

  if (response.status === 401 && auth) {
    try {
      await refreshAccessToken();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        // The session is really over. A network problem, by contrast, signs nobody out.
        accessToken = null;
        unauthorizedHandler?.();
        throw await toApiError(response);
      }
      throw error;
    }
    response = await send(path, method, body, accessToken); // retried exactly once
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
