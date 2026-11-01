export type MonitorStatus = "UP" | "DEGRADED" | "DOWN" | "PAUSED" | "PENDING";

const LABELS: Record<MonitorStatus, string> = {
  UP: "Up",
  DEGRADED: "Degraded",
  DOWN: "Down",
  PAUSED: "Paused",
  PENDING: "Pending",
};

/** The status is always written out, so it is never conveyed by color alone. */
export function StatusBadge({ status }: { status: MonitorStatus }) {
  return <span className={`badge badge--${status.toLowerCase()}`}>{LABELS[status]}</span>;
}
