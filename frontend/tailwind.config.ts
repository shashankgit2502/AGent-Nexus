import type { Config } from "tailwindcss";

/**
 * Tailwind v3 config.
 *
 * The reference (`reference/nex-agi`) is Tailwind v4 and declares fonts in an
 * `@theme` block in `index.css`. v3 has no `@theme`, so the font families move
 * here. The `var(--font-*)` values are populated by `next/font` in
 * `app/layout.tsx` (Inter + JetBrains Mono), with the same fallback stacks the
 * reference used. Accent + base background follow the reference theme
 * (FRONTEND_INTEGRATION_PLAN §3); `emerald` is Tailwind's built-in palette
 * whose 500 is `#10b981`, the reference accent.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: [
          "var(--font-mono)",
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
      },
      colors: {
        // The reference's matte obsidian base (#050506) and emerald accent
        // (#10b981 == emerald-500). Exposed as named tokens for non-arbitrary use.
        obsidian: "#050506",
        accent: {
          DEFAULT: "#10b981",
        },
      },
    },
  },
  plugins: [],
};

export default config;
