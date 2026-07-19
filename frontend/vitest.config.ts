import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Vitest config.
 *
 * The Slice-1 acceptance test is the **pure** session reducer fold — it imports
 * a plain function (`store/session-reducer.ts`) and exercises it over the mock
 * AG-UI stream. No React, no DOM: the `node` environment is correct and keeps
 * the test deps minimal (R2 — don't pull jsdom/RTL we don't use yet).
 */
export default defineConfig({
  // Mirror the tsconfig `@/*` path alias so tests resolve project imports the
  // same way Next/tsc do (the `@` root maps to the frontend directory).
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
  },
});
