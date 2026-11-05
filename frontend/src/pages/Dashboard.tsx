import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/auth-context";
import { GlassButton } from "../components/glass/GlassButton";
import { GlassCard } from "../components/glass/GlassCard";
import { Navbar } from "../components/layout/Navbar";

/** A placeholder that proves the login works. Phase 7 builds the real dashboard here. */
export function Dashboard() {
  const { user, logout } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  async function onLogout() {
    setSigningOut(true);
    await logout(); // never throws; the route guard then moves us to the login page
  }

  return (
    <div className="shell">
      <Navbar>
        <Link className="nav-link" to="/styleguide">
          Style guide
        </Link>
        <GlassButton variant="secondary" loading={signingOut} onClick={onLogout}>
          Log out
        </GlassButton>
      </Navbar>
      <GlassCard>
        <h1>Dashboard</h1>
        <p className="shell__text">
          Signed in as <strong>{user?.email}</strong>
        </p>
        <p className="shell__text">Your monitors will appear here in the next phase.</p>
      </GlassCard>
    </div>
  );
}
