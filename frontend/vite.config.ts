import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Dev-only: target for the Vite dev-server proxy. This never reaches the
// production bundle (the built app uses a relative /api/v1 via runtime-config.js
// behind the Caddy reverse proxy).
const API_URL = process.env.API_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [
    react(),
    // Bundle analyzer: run `npx vite-bundle-visualizer` to generate stats.
    // Not included here by default to avoid ESM import issues.
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 3000,
    strictPort: false, // auto-increment if 3000 is taken
    proxy: {
      "/api": {
        target: API_URL,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false, // no source maps in production (no source leak, smaller)
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes("node_modules/react") ||
            id.includes("node_modules/react-dom") ||
            id.includes("node_modules/react-router")
          ) {
            return "vendor";
          }
          if (id.includes("node_modules/recharts")) {
            return "charts";
          }
          if (id.includes("node_modules/lucide-react")) {
            return "icons";
          }
        },
      },
    },
  },
});
