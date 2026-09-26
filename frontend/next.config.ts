import type { NextConfig } from "next";
import { dropBlankAuthUrls } from "./src/lib/env";

// Environment: the npm scripts load the repo-root .env (dotenv-cli) before Next
// starts, so every Next process inherits it. On Vercel the variables come from
// the project settings instead. A blank NEXTAUTH_URL would crash the build's
// prerendering, so it is cleared here (and at runtime in src/instrumentation.ts).
dropBlankAuthUrls();

/** Baseline security headers for every route. */
const securityHeaders = [
  // Forbid framing (clickjacking protection for the sign-in flow and dashboard)
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
