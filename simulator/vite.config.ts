import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The simulator talks to OpenVan Core over the same origin via this dev proxy,
// so no CORS juggling and no hard-coded host. Override the target with
// OPENVAN_CORE (e.g. when Core runs on another machine on the van's network).
const core = process.env.OPENVAN_CORE ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: core, changeOrigin: true },
      "/ws": { target: core, ws: true, changeOrigin: true },
    },
  },
});
