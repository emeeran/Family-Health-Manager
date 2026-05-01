import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

const API_URL = process.env.API_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
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
  },
});
