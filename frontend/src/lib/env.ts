/**
 * NextAuth parses NEXTAUTH_URL when its modules load and crashes on an empty
 * string ("Invalid URL"). Treat blank values as unset so it falls back to
 * VERCEL_URL on Vercel (and localhost in development).
 */
export function dropBlankAuthUrls(): void {
  for (const key of ["NEXTAUTH_URL", "NEXTAUTH_URL_INTERNAL"]) {
    if (process.env[key] !== undefined && !process.env[key]?.trim()) delete process.env[key];
  }
}

/** Public base URL of the app, used for links in emails. */
export function appBaseUrl(): string | null {
  const explicit = process.env.NEXTAUTH_URL?.trim();
  if (explicit) return explicit.replace(/\/$/, "");
  // Vercel system variables (hostnames without protocol)
  const vercelHost = process.env.VERCEL_PROJECT_PRODUCTION_URL || process.env.VERCEL_URL;
  return vercelHost ? `https://${vercelHost}` : null;
}
