import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../../auth/auth-context";
import { useTheme } from "../../hooks/useTheme";
import { cx } from "../../lib/cx";
import { GlassButton } from "../glass/GlassButton";
import { Navbar } from "./Navbar";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/monitors", label: "Monitors", end: false },
];

/** The frame around every signed-in page: top bar, sidebar and the page itself. */
export function AppShell() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const [signingOut, setSigningOut] = useState(false);
  const next = theme === "dark" ? "light" : "dark";

  async function onLogout() {
    setSigningOut(true);
    await logout(); // never throws; the route guard then moves us to the login page
  }

  return (
    <div className="app-shell">
      <Navbar>
        <span className="app-shell__user">{user?.email}</span>
        <GlassButton variant="secondary" onClick={toggle}>
          Switch to {next} theme
        </GlassButton>
        <GlassButton variant="secondary" loading={signingOut} onClick={onLogout}>
          Log out
        </GlassButton>
      </Navbar>

      <div className="app-shell__body">
        <nav className="glass sidebar app-shell__nav" aria-label="Main">
          <ul>
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cx("sidebar__link", isActive && "sidebar__link--active")
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main className="app-shell__main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
