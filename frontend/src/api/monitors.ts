import { apiFetch } from "./client";
import type { MonitorStatus } from "../components/glass/StatusBadge";

/** Matches MonitorOut in the backend. */
export interface Monitor {
  id: string;
  name: string;
  url: string;
  method: "GET" | "HEAD";
  interval_seconds: number;
  timeout_seconds: number;
  expected_status: number;
  keyword: string | null;
  is_paused: boolean;
  status: MonitorStatus;
  consecutive_failures: number;
  consecutive_successes: number;
  consecutive_slow: number;
  next_check_at: string;
  last_checked_at: string | null;
  ssl_expires_at: string | null;
  created_at: string;
}

export interface MonitorPage {
  items: Monitor[];
  total: number;
  limit: number;
  offset: number;
}

/** What the form sends. A null keyword means "no keyword check". */
export interface MonitorInput {
  name: string;
  url: string;
  method: "GET" | "HEAD";
  interval_seconds: number;
  timeout_seconds: number;
  expected_status: number;
  keyword: string | null;
}

// A user can have at most 20 monitors, so one page of 100 always holds them all.
export function listMonitors(): Promise<MonitorPage> {
  return apiFetch<MonitorPage>("/api/v1/monitors?limit=100");
}

export function createMonitor(input: MonitorInput): Promise<Monitor> {
  return apiFetch<Monitor>("/api/v1/monitors", { method: "POST", body: input });
}

export function updateMonitor(id: string, input: MonitorInput): Promise<Monitor> {
  return apiFetch<Monitor>(`/api/v1/monitors/${id}`, { method: "PATCH", body: input });
}

export function deleteMonitor(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/monitors/${id}`, { method: "DELETE" });
}

export function pauseMonitor(id: string): Promise<Monitor> {
  return apiFetch<Monitor>(`/api/v1/monitors/${id}/pause`, { method: "POST" });
}

export function resumeMonitor(id: string): Promise<Monitor> {
  return apiFetch<Monitor>(`/api/v1/monitors/${id}/resume`, { method: "POST" });
}
