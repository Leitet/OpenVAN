import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// The product UI talks to OpenVan Core over the same origin via this dev proxy,
// so no CORS juggling and no hard-coded host. Override the target with
// OPENVAN_CORE (e.g. when Core runs on another machine on the van's network).
const core = process.env.OPENVAN_CORE ?? "http://127.0.0.1:8000";
const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const shared = fileURLToPath(new URL("../shared", import.meta.url));

export default defineConfig({
  plugins: [react()],
  // ../shared is source shared with the bench app (api client, types, WS hook).
  resolve: { alias: { "@shared": shared } },
  server: {
    port: 5173,
    fs: { allow: [repoRoot] },
    proxy: {
      "/api": { target: core, changeOrigin: true },
      "/ws": { target: core, ws: true, changeOrigin: true },
    },
  },
});
