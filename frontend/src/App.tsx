import { AnimatedBackground } from "./components/layout/AnimatedBackground";
import { useTheme } from "./hooks/useTheme";

/** A first page to check the tokens, the glass surface and the theme. Part C adds real routes. */
export default function App() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";

  return (
    <>
      <AnimatedBackground />
      <main className="page">
        <header className="page__header">
          <h1 className="page__title">UptimeGlass</h1>
          <button type="button" className="theme-toggle" onClick={toggle}>
            Switch to {next} theme
          </button>
        </header>

        <section className="glass card" aria-labelledby="demo-heading">
          <h2 id="demo-heading">Liquid glass surface</h2>
          <p className="card__text">
            This card blurs the drifting gradients behind it. The status colors below keep
            their contrast in both themes.
          </p>
          <div className="status-row">
            <span className="pill pill--up">Up</span>
            <span className="pill pill--degraded">Degraded</span>
            <span className="pill pill--down">Down</span>
          </div>
        </section>
      </main>
    </>
  );
}
