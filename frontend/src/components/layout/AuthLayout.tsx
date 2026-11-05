import type { ReactNode } from "react";

import { GlassCard } from "../glass/GlassCard";

interface AuthLayoutProps {
  title: string;
  children: ReactNode;
  footer: ReactNode;
}

/** A centered glass card for the login and register forms. */
export function AuthLayout({ title, children, footer }: AuthLayoutProps) {
  return (
    <main className="center-page">
      <GlassCard padded={false} className="auth-card">
        <h1>{title}</h1>
        {children}
        <p className="auth-footer">{footer}</p>
      </GlassCard>
    </main>
  );
}
