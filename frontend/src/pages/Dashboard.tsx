import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Monitor } from "../api/monitors";
import { EmptyState } from "../components/glass/EmptyState";
import { GlassButton } from "../components/glass/GlassButton";
import { GlassCard } from "../components/glass/GlassCard";
import { Skeleton } from "../components/glass/Skeleton";
import { StatusBadge } from "../components/glass/StatusBadge";
import { useMonitors, useOpenIncidentCount } from "../hooks/useMonitors";
import { cx } from "../lib/cx";
import { errorMessage } from "../lib/errors";
import { timeAgo } from "../lib/format";

function StatCard({
  id,
  label,
  value,
  tone,
}: {
  id: string;
  label: string;
  value: ReactNode;
  tone?: "up" | "degraded" | "down";
}) {
  return (
    <GlassCard className={cx("stat", tone && `stat--${tone}`)} data-testid={`stat-${id}`}>
      <span className="stat__label">{label}</span>
      <span className="stat__value">{value}</span>
    </GlassCard>
  );
}

// DOWN first, then DEGRADED.
const RANK: Record<string, number> = { DOWN: 0, DEGRADED: 1 };

export function Dashboard() {
  const monitors = useMonitors();
  const incidents = useOpenIncidentCount();
  const items: Monitor[] = monitors.data?.items ?? [];
  const count = (status: Monitor["status"]) => items.filter((m) => m.status === status).length;
  const attention = items
    .filter((m) => m.status === "DOWN" || m.status === "DEGRADED")
    .sort((a, b) => RANK[a.status] - RANK[b.status]);

  // A number once loaded, a placeholder while loading.
  const number = (value: number): ReactNode =>
    monitors.isPending ? <Skeleton width="3rem" height="1.75rem" /> : value;

  let incidentValue: ReactNode;
  if (incidents.isPending) incidentValue = <Skeleton width="3rem" height="1.75rem" />;
  else if (incidents.isError) incidentValue = "–";
  else incidentValue = incidents.data;

  let attentionContent: ReactNode;
  if (monitors.isError) {
    attentionContent = (
      <div className="error-card">
        <p role="alert">{errorMessage(monitors.error)}</p>
        <GlassButton variant="secondary" onClick={() => monitors.refetch()}>
          Try again
        </GlassButton>
      </div>
    );
  } else if (monitors.isPending) {
    attentionContent = (
      <div className="skeleton-stack" aria-busy="true">
        <Skeleton width="50%" />
        <Skeleton width="35%" />
      </div>
    );
  } else if (items.length === 0) {
    attentionContent = (
      <EmptyState
        icon="📡"
        title="No monitors yet"
        description="Add your first URL and UptimeGlass starts checking it."
        action={
          <Link className="glass-button glass-button--primary" to="/monitors">
            Add your first monitor
          </Link>
        }
      />
    );
  } else if (attention.length === 0) {
    attentionContent = <p className="page-sub">All monitors are healthy.</p>;
  } else {
    attentionContent = (
      <ul className="attention">
        {attention.map((monitor) => (
          <li key={monitor.id} className="attention__item">
            <span className="attention__name">{monitor.name}</span>
            <StatusBadge status={monitor.status} />
            <span className="page-sub">Checked {timeAgo(monitor.last_checked_at)}</span>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <>
      <div className="page-head">
        <h1>Dashboard</h1>
      </div>

      <section className="stats" aria-label="Overview">
        <StatCard id="total" label="Total monitors" value={number(items.length)} />
        <StatCard id="up" label="Up" value={number(count("UP"))} tone="up" />
        <StatCard id="degraded" label="Degraded" value={number(count("DEGRADED"))} tone="degraded" />
        <StatCard id="down" label="Down" value={number(count("DOWN"))} tone="down" />
        <StatCard id="incidents" label="Open incidents" value={incidentValue} />
      </section>

      <GlassCard aria-labelledby="attention-heading">
        <h2 id="attention-heading" className="section-title">
          Needs attention
        </h2>
        {attentionContent}
      </GlassCard>
    </>
  );
}
