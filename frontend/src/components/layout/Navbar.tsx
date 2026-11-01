import type { ReactNode } from "react";

/** Top bar: the brand on the left and any actions (like the theme button) on the right. */
export function Navbar({ children }: { children?: ReactNode }) {
  return (
    <header className="glass navbar">
      <span className="navbar__brand">UptimeGlass</span>
      <div className="navbar__actions">{children}</div>
    </header>
  );
}
