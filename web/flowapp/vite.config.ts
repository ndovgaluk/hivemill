import { readFileSync } from "node:fs";

import react from "@vitejs/plugin-react";
import { loadEnv, type Plugin } from "vite";
import { defineConfig } from "vitest/config";

import { DEFAULT_FACTORY_URL, DEV_PORT, DevEnv, FIXTURE_ID, SCOPES } from "./src/constants.ts";

const FIXTURE_RE = new RegExp(`^/api/flow/(${SCOPES.join("|")})/${FIXTURE_ID}\\.json`);
const PROXIED = ["/api", "/static/app.css", "/static/theme.js", "/static/fonts"];

/** Dev server only: /api/flow/{scope}/fixture.json answers with src/fixtures/{scope}.json, before the proxy. */
function fixtures(): Plugin {
  return {
    name: "flow-fixtures",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const m = FIXTURE_RE.exec(req.url ?? "");
        if (!m) return next();
        res.setHeader("Content-Type", "application/json");
        res.end(readFileSync(new URL(`./src/fixtures/${m[1]}.json`, import.meta.url)));
      });
    },
  };
}

// Fixed file names (no hashes): the Python page links /static/flow/flow.js and flow.css directly.
export default defineConfig(({ mode, command }) => {
  const target = loadEnv(mode, ".")[DevEnv.FactoryUrl] || DEFAULT_FACTORY_URL;
  return {
    plugins: [react(), fixtures()],
    base: command === "build" ? "/static/flow/" : "/",
    server: {
      port: DEV_PORT,
      strictPort: true,
      // changeOrigin: factory serve only accepts its own Host header
      proxy: Object.fromEntries(PROXIED.map((p) => [p, { target, changeOrigin: true }])),
    },
    build: {
      outDir: "../static/flow",
      emptyOutDir: true,
      cssCodeSplit: false,
      rollupOptions: {
        input: "src/main.tsx",
        output: {
          entryFileNames: "flow.js",
          assetFileNames: "flow[extname]",
          codeSplitting: false,
        },
      },
    },
    test: {
      environment: "jsdom",
      include: ["src/__tests__/**/*.test.{ts,tsx}"],
      setupFiles: ["src/__tests__/setup.ts"],
    },
  };
});
