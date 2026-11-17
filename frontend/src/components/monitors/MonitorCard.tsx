import type { Monitor } from "../../api/monitors";
import { formatInterval, timeAgo } from "../../lib/format";
import { GlassButton } from "../glass/GlassButton";
import { GlassCard } from "../glass/GlassCard";
import { StatusBadge } from "../glass/StatusBadge";

interface MonitorCardProps {
  monitor: Monitor;
  busy: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

export function MonitorCard({ monitor, busy, onToggle, onEdit, onDelete }: MonitorCardProps) {
  const toggleLabel = monitor.is_paused ? "Resume" : "Pause";

  return (
    <li>
      <GlassCard className="monitor-card">
        <div className="monitor-card__main">
          <div className="monitor-card__title">
            <h2 className="monitor-card__name">{monitor.name}</h2>
            <StatusBadge status={monitor.status} />
          </div>
          <p className="monitor-card__url">{monitor.url}</p>
          <p className="monitor-card__meta">
            Every {formatInterval(monitor.interval_seconds)} · Checked{" "}
            {timeAgo(monitor.last_checked_at)}
          </p>
        </div>
        <div className="monitor-card__actions">
          <GlassButton
            variant="secondary"
            loading={busy}
            onClick={onToggle}
            aria-label={`${toggleLabel} ${monitor.name}`}
          >
            {toggleLabel}
          </GlassButton>
          <GlassButton
            variant="secondary"
            disabled={busy}
            onClick={onEdit}
            aria-label={`Edit ${monitor.name}`}
          >
            Edit
          </GlassButton>
          <GlassButton
            variant="danger"
            disabled={busy}
            onClick={onDelete}
            aria-label={`Delete ${monitor.name}`}
          >
            Delete
          </GlassButton>
        </div>
      </GlassCard>
    </li>
  );
}
