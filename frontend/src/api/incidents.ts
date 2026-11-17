import { apiFetch } from "./client";

export interface Incident {
  id: string;
  monitor_id: string;
  started_at: string;
  resolved_at: string | null;
  status: "open" | "resolved";
  cause: string;
  details: Record<string, unknown>;
  ai_summary: string | null;
}

export interface IncidentPage {
  items: Incident[];
  total: number;
  limit: number;
  offset: number;
}

/** Only the total is needed, so ask for one row. */
export async function countOpenIncidents(): Promise<number> {
  const page = await apiFetch<IncidentPage>("/api/v1/incidents?status=open&limit=1");
  return page.total;
}
