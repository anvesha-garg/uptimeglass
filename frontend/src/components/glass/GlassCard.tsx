import type { HTMLAttributes } from "react";

import { cx } from "../../lib/cx";

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  padded?: boolean;
}

export function GlassCard({ padded = true, className, ...rest }: GlassCardProps) {
  return <div {...rest} className={cx("glass", padded && "glass-card--padded", className)} />;
}
