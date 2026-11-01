import { AnimatedBackground } from "./components/layout/AnimatedBackground";
import { ToastProvider } from "./components/glass/ToastProvider";
import { StyleGuide } from "./pages/StyleGuide";

/** Part C replaces this with real routes. For now the style guide is the page. */
export default function App() {
  return (
    <ToastProvider>
      <AnimatedBackground />
      <StyleGuide />
    </ToastProvider>
  );
}
