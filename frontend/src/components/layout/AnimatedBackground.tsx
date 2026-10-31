/** Decorative background. Hidden from screen readers and ignores the mouse. */
export function AnimatedBackground() {
  return (
    <div className="bg" aria-hidden="true" data-testid="animated-background">
      <span className="bg__blob bg__blob--1" />
      <span className="bg__blob bg__blob--2" />
      <span className="bg__blob bg__blob--3" />
    </div>
  );
}
