import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Regression guard for the "white dropdown" bug (R3).
 *
 * Native <select> popups are painted by the user-agent, not the DOM. The fix has
 * two structural pillars that, if removed, silently bring the unreadable
 * white-on-white dropdown back:
 *   1. `color-scheme: dark` on <html>  → native controls paint in the dark theme.
 *   2. explicit solid-dark `option` colours → popup rows stay legible everywhere.
 *   3. the shared SelectInput hides the native arrow and draws its own chevron.
 *
 * The test suite runs in the `node` env (no DOM), so we assert over source/CSS
 * content rather than a render — the failure mode here is a declaration being
 * deleted, which file content catches precisely.
 */
const read = (rel: string): string =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

describe("dropdown dark-theme fix", () => {
  const css = read("./globals.css");
  const primitives = read("../components/crud/primitives.tsx");

  it("declares the dark color-scheme so native control popups are not white", () => {
    expect(css).toMatch(/color-scheme:\s*dark/);
  });

  it("gives <option>/<optgroup> an explicit solid-dark background and light text", () => {
    expect(css).toMatch(/select option[\s\S]*background-color:\s*#0c0f0e/);
    expect(css).toMatch(/select option[\s\S]*color:\s*#e5e7eb/);
  });

  it("SelectInput hides the native arrow and renders its own chevron", () => {
    expect(primitives).toContain("appearance-none");
    expect(primitives).toContain("ChevronDown");
  });
});
