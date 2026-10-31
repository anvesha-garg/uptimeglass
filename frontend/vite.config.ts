import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first and is slow.
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      // The browser talks only to this origin. The proxy forwards /api to the backend,
      // so the refresh cookie stays same-site (the plan for production is the same).
      "/api": { target: "http://127.0.0.1:8000" },
    },
  },
});
