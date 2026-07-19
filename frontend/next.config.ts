import type { NextConfig } from "next";

/**
 * Next.js config.
 *
 * The frontend talks to FastAPI directly via `NEXT_PUBLIC_API_BASE_URL` /
 * `NEXT_PUBLIC_WS_URL` (see `lib/api/client.ts`, `lib/ws/agui-client.ts`), so no
 * rewrite proxy is needed for REST/WS. We keep the config minimal and explicit
 * rather than hiding the backend origin behind a same-origin rewrite — the org
 * header + base-URL seam lives in `lib/`, which is the single place to change it.
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
