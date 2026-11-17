import { useState } from "react";

import type { Monitor } from "../api/monitors";
import { EmptyState } from "../components/glass/EmptyState";
import { GlassButton } from "../components/glass/GlassButton";
import { GlassCard } from "../components/glass/GlassCard";
import { GlassModal } from "../components/glass/GlassModal";
import { Skeleton } from "../components/glass/Skeleton";
import { useToast } from "../components/glass/toast-context";
import { MonitorCard } from "../components/monitors/MonitorCard";
import { MonitorForm } from "../components/monitors/MonitorForm";
import { useMonitorAction, useMonitors } from "../hooks/useMonitors";
import { errorMessage } from "../lib/errors";

const MAX_MONITORS = 20; // the backend enforces this too

export function Monitors() {
  const query = useMonitors();
  const action = useMonitorAction();
  const { show } = useToast();
  // null = no form; { monitor: null } = create; { monitor } = edit
  const [form, setForm] = useState<{ monitor: Monitor | null } | null>(null);
  const [toDelete, setToDelete] = useState<Monitor | null>(null);

  const monitors = query.data?.items ?? [];
  const atLimit = monitors.length >= MAX_MONITORS;

  function toggle(monitor: Monitor) {
    const kind = monitor.is_paused ? "resume" : "pause";
    action.mutate(
      { id: monitor.id, action: kind },
      {
        onSuccess: () => show(kind === "pause" ? "Monitor paused." : "Monitor resumed.", "success"),
        onError: (error) => show(errorMessage(error), "error"),
      },
    );
  }

  function confirmDelete() {
    if (!toDelete) return;
    action.mutate(
      { id: toDelete.id, action: "delete" },
      {
        onSuccess: () => {
          show("Monitor deleted.", "success");
          setToDelete(null);
        },
        onError: (error) => show(errorMessage(error), "error"),
      },
    );
  }

  let content;
  if (query.isPending) {
    content = (
      <GlassCard aria-busy="true">
        <div className="skeleton-stack">
          <Skeleton width="40%" height="1.25rem" />
          <Skeleton width="70%" />
          <Skeleton width="55%" />
        </div>
      </GlassCard>
    );
  } else if (query.isError) {
    content = (
      <GlassCard className="error-card">
        <p role="alert">{errorMessage(query.error)}</p>
        <GlassButton variant="secondary" onClick={() => query.refetch()}>
          Try again
        </GlassButton>
      </GlassCard>
    );
  } else if (monitors.length === 0) {
    content = (
      <GlassCard>
        <EmptyState
          icon="📡"
          title="No monitors yet"
          description="Add your first URL and UptimeGlass starts checking it."
          action={
            <GlassButton onClick={() => setForm({ monitor: null })}>
              Add your first monitor
            </GlassButton>
          }
        />
      </GlassCard>
    );
  } else {
    content = (
      <ul className="monitor-list">
        {monitors.map((monitor) => (
          <MonitorCard
            key={monitor.id}
            monitor={monitor}
            busy={action.isPending && action.variables?.id === monitor.id}
            onToggle={() => toggle(monitor)}
            onEdit={() => setForm({ monitor })}
            onDelete={() => setToDelete(monitor)}
          />
        ))}
      </ul>
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Monitors</h1>
          <p className="page-sub">
            {query.data ? `${monitors.length} of ${MAX_MONITORS} monitors` : "Your monitors"}
          </p>
        </div>
        <GlassButton disabled={atLimit} onClick={() => setForm({ monitor: null })}>
          Add monitor
        </GlassButton>
      </div>

      {content}

      {form && (
        <MonitorForm
          key={form.monitor?.id ?? "new"}
          monitor={form.monitor}
          onClose={() => setForm(null)}
        />
      )}

      <GlassModal open={toDelete !== null} onClose={() => setToDelete(null)} title="Delete monitor?">
        <p>
          This removes “{toDelete?.name}” and its history. This cannot be undone.
        </p>
        <div className="monitor-form__actions">
          <GlassButton
            variant="danger"
            loading={action.isPending && action.variables?.action === "delete"}
            onClick={confirmDelete}
          >
            Delete
          </GlassButton>
          <GlassButton variant="secondary" onClick={() => setToDelete(null)}>
            Cancel
          </GlassButton>
        </div>
      </GlassModal>
    </>
  );
}
