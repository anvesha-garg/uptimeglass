import { Link } from "react-router-dom";

import { GlassCard } from "../components/glass/GlassCard";

export function NotFound() {
  return (
    <main className="center-page">
      <GlassCard className="auth-card">
        <h1>Page not found</h1>
        <p className="auth-footer">
          <Link to="/">Go to the start page</Link>
        </p>
      </GlassCard>
    </main>
  );
}
