/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";

import { injectCsp } from "./src/lib/csp";

const DEFAULT_API = "http://127.0.0.1:8000"; // same default as src/lib/api/client.ts

/** Adds the Content-Security-Policy to the built index.html (not to the dev server). */
function contentSecurityPolicy(apiBaseUrl: string): Plugin {
  return {
    name: "mantle-csp",
    apply: "build",
    transformIndexHtml: (html) => injectCsp(html, apiBaseUrl),
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [react(), tailwindcss(), contentSecurityPolicy(env.VITE_API_BASE_URL || DEFAULT_API)],
    server: {
      // The backend allows these origins in CORS; keep the port fixed.
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
    },
    // Same origin as the dev server, which the backend's CORS allows; stop `npm run dev` first.
    preview: { host: "127.0.0.1", port: 5173, strictPort: true },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      coverage: {
        provider: "v8",
        include: ["src/lib/**/*.ts"],
        exclude: ["src/lib/api/schema.ts", "src/**/*.test.ts"],
        reporter: ["text", "text-summary"],
      },
    },
  };
});
