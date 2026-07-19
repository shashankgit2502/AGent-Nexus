import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Providers } from "@/app/providers";
import { AppShell } from "@/components/app-shell";
import { ThreeMeshBackground } from "@/components/three-mesh-background";
import "@/app/globals.css";

/*
 * Fonts via next/font (self-hosted, no layout shift) replacing the reference's
 * Google Fonts @import. The CSS variables feed tailwind.config.ts fontFamily.
 */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["300", "400", "500", "600", "700", "800", "900"],
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "NEX AGI",
  description: "Decentralized multi-agent operating system — collaborative ReAct mesh.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen bg-[#050506] text-[#fafafa] flex flex-col font-sans antialiased overflow-x-hidden selection:bg-emerald-500/20 selection:text-emerald-300 relative">
        {/* Ported artistic background layers */}
        <div className="artistic-background" />
        <div className="artistic-grid" />

        {/* Global animated agent-mesh backdrop — sits behind every route's content. */}
        <ThreeMeshBackground />

        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
