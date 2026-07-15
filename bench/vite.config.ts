import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// The bench talks to the same OpenVan Core as the product UI, over the dev
// proxy. It runs on its own port so the two surfaces never get confused.
const core = process.env.OPENVAN_CORE ?? "http://127.0.0.1:8000";
const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const shared = fileURLToPath(new URL("../shared", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@shared": shared } },
  server: {
    port: 5174,
    fs: { allow: [repoRoot] },
    proxy: {
      "/api": { target: core, changeOrigin: true },
      "/ws": { target: core, ws: true, changeOrigin: true },
    },
  },
});
