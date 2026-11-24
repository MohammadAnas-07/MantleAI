/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

import { screenshots } from "./screenshots-plugin";
import { injectCsp } from "./src/csp";

/** Adds the Content-Security-Policy to the built index.html (not to the dev server). */
function contentSecurityPolicy(): Plugin {
  return { name: "landing-csp", apply: "build", transformIndexHtml: (html) => injectCsp(html) };
}

export default defineConfig({
  // Relative asset paths, so the built page also works under a GitHub Pages sub-path.
  base: "./",
  plugins: [react(), tailwindcss(), contentSecurityPolicy(), screenshots("public")],
  build: {
    // Inline nothing: a data: URL would need an exception in the CSP.
    assetsInlineLimit: 0,
  },
  server: { host: "127.0.0.1", port: 5174, strictPort: true },
  preview: { host: "127.0.0.1", port: 5174, strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
