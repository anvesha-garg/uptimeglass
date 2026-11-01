import { cx } from "../../lib/cx";

interface SkeletonProps {
  width?: string;
  height?: string;
  className?: string;
}

/** A shimmering placeholder. Hidden from screen readers: mark the loading area aria-busy. */
export function Skeleton({ width = "100%", height = "1rem", className }: SkeletonProps) {
  return (
    <span
      className={cx("skeleton", className)}
      style={{ width, height }}
      aria-hidden="true"
      data-testid="skeleton"
    />
  );
}
