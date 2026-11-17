import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { countOpenIncidents } from "../api/incidents";
import {
  createMonitor,
  deleteMonitor,
  listMonitors,
  pauseMonitor,
  resumeMonitor,
  updateMonitor,
} from "../api/monitors";
import type { MonitorInput } from "../api/monitors";

export const MONITORS_KEY = ["monitors"] as const;

// Phase 8 replaces polling with live WebSocket events.
const POLL_MS = 15_000;

export function useMonitors() {
  return useQuery({ queryKey: MONITORS_KEY, queryFn: listMonitors, refetchInterval: POLL_MS });
}

export function useOpenIncidentCount() {
  return useQuery({
    queryKey: ["incidents", "open-count"],
    queryFn: countOpenIncidents,
    refetchInterval: POLL_MS,
  });
}

/** Creates a monitor, or updates one when `editingId` is set. */
export function useSaveMonitor(editingId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: MonitorInput) =>
      editingId ? updateMonitor(editingId, input) : createMonitor(input),
    // Returning the promise makes the mutation wait for the refreshed list.
    onSuccess: () => client.invalidateQueries({ queryKey: MONITORS_KEY }),
  });
}

export type MonitorAction = "pause" | "resume" | "delete";

export function useMonitorAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, action }: { id: string; action: MonitorAction }) => {
      if (action === "delete") await deleteMonitor(id);
      else if (action === "pause") await pauseMonitor(id);
      else await resumeMonitor(id);
    },
    onSuccess: () => client.invalidateQueries({ queryKey: MONITORS_KEY }),
  });
}
