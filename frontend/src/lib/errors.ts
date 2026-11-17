import { ApiError } from "../api/client";

/** A message that is safe to show: the server's own text, or a generic one. */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}
