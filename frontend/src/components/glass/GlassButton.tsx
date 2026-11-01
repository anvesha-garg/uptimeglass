import type { ButtonHTMLAttributes } from "react";

import { cx } from "../../lib/cx";

type Variant = "primary" | "secondary" | "danger";

interface GlassButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

export function GlassButton({
  variant = "primary",
  loading = false,
  disabled,
  className,
  children,
  type = "button",
  ...rest
}: GlassButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={cx("glass-button", `glass-button--${variant}`, className)}
      // A loading button is also disabled, so it cannot be submitted twice.
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading && <span className="spinner" aria-hidden="true" />}
      <span>{children}</span>
    </button>
  );
}
