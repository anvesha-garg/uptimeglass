import { useState } from "react";

import { EmptyState } from "../components/glass/EmptyState";
import { GlassButton } from "../components/glass/GlassButton";
import { GlassCard } from "../components/glass/GlassCard";
import { GlassInput } from "../components/glass/GlassInput";
import { GlassModal } from "../components/glass/GlassModal";
import { Skeleton } from "../components/glass/Skeleton";
import { StatusBadge } from "../components/glass/StatusBadge";
import type { MonitorStatus } from "../components/glass/StatusBadge";
import { useToast } from "../components/glass/toast-context";
import { Navbar } from "../components/layout/Navbar";
import { Sidebar } from "../components/layout/Sidebar";
import type { NavItem } from "../components/layout/Sidebar";
import { useTheme } from "../hooks/useTheme";
import "./styleguide.css";

const STATUSES: MonitorStatus[] = ["UP", "DEGRADED", "DOWN", "PAUSED", "PENDING"];

const SECTIONS: NavItem[] = [
  { id: "buttons", label: "Buttons", href: "#buttons" },
  { id: "inputs", label: "Inputs", href: "#inputs" },
  { id: "badges", label: "Status badges", href: "#badges" },
  { id: "loading", label: "Loading and empty", href: "#loading" },
  { id: "overlays", label: "Modal and toasts", href: "#overlays" },
];

/** Shows every component in every state, in both themes. Part C puts it on a route. */
export function StyleGuide() {
  const { theme, toggle } = useTheme();
  const { show } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const next = theme === "dark" ? "light" : "dark";

  return (
    <div className="guide">
      <Navbar>
        <GlassButton variant="secondary" onClick={toggle}>
          Switch to {next} theme
        </GlassButton>
      </Navbar>

      <div className="guide__body">
        <Sidebar className="guide__sidebar" items={SECTIONS} currentId="buttons" />

        <main className="guide__main">
          <h1 className="visually-title">Style guide</h1>

          <GlassCard id="buttons" className="guide__section" aria-labelledby="h-buttons">
            <h2 id="h-buttons">Buttons</h2>
            <div className="guide__row">
              <GlassButton>Primary</GlassButton>
              <GlassButton variant="secondary">Secondary</GlassButton>
              <GlassButton variant="danger">Danger</GlassButton>
              <GlassButton disabled>Disabled</GlassButton>
              <GlassButton loading={loading} onClick={() => setLoading((value) => !value)}>
                {loading ? "Saving" : "Click to load"}
              </GlassButton>
            </div>
          </GlassCard>

          <GlassCard id="inputs" className="guide__section" aria-labelledby="h-inputs">
            <h2 id="h-inputs">Inputs</h2>
            <div className="guide__form">
              <GlassInput label="Monitor name" placeholder="My website" />
              <GlassInput
                label="URL"
                hint="Must start with http:// or https://"
                placeholder="https://example.com"
              />
              <GlassInput label="Interval (seconds)" defaultValue="30" error="Minimum is 60." />
            </div>
          </GlassCard>

          <GlassCard id="badges" className="guide__section" aria-labelledby="h-badges">
            <h2 id="h-badges">Status badges</h2>
            <div className="guide__row">
              {STATUSES.map((status) => (
                <StatusBadge key={status} status={status} />
              ))}
            </div>
          </GlassCard>

          <GlassCard id="loading" className="guide__section" aria-labelledby="h-loading">
            <h2 id="h-loading">Loading and empty</h2>
            <div className="guide__skeletons" aria-busy="true">
              <Skeleton width="60%" height="1.25rem" />
              <Skeleton />
              <Skeleton width="80%" />
            </div>
            <EmptyState
              icon="📡"
              title="No monitors yet"
              description="Add your first URL and UptimeGlass starts checking it."
              action={<GlassButton>Add monitor</GlassButton>}
            />
          </GlassCard>

          <GlassCard id="overlays" className="guide__section" aria-labelledby="h-overlays">
            <h2 id="h-overlays">Modal and toasts</h2>
            <div className="guide__row">
              <GlassButton variant="secondary" onClick={() => setModalOpen(true)}>
                Open modal
              </GlassButton>
              <GlassButton variant="secondary" onClick={() => show("Monitor saved.", "success")}>
                Success toast
              </GlassButton>
              <GlassButton variant="secondary" onClick={() => show("Something went wrong.", "error")}>
                Error toast
              </GlassButton>
              <GlassButton variant="secondary" onClick={() => show("Checks run every minute.")}>
                Info toast
              </GlassButton>
            </div>
          </GlassCard>
        </main>
      </div>

      <GlassModal open={modalOpen} onClose={() => setModalOpen(false)} title="Delete monitor?">
        <p>This removes the monitor and its history. This cannot be undone.</p>
        <div className="guide__row" style={{ marginTop: "var(--space-4)" }}>
          <GlassButton variant="danger" onClick={() => setModalOpen(false)}>
            Delete
          </GlassButton>
          <GlassButton variant="secondary" onClick={() => setModalOpen(false)}>
            Cancel
          </GlassButton>
        </div>
      </GlassModal>
    </div>
  );
}
