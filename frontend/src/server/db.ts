import "server-only";
import { neon, type NeonQueryFunction } from "@neondatabase/serverless";

let client: NeonQueryFunction<false, false> | null = null;

/**
 * Neon's HTTP driver: one stateless HTTPS request per query, so there are no
 * connection pools to exhaust on serverless. Created lazily so `next build`
 * doesn't need DATABASE_URL.
 */
export function db(): NeonQueryFunction<false, false> {
  if (!client) {
    const url = process.env.DATABASE_URL;
    if (!url) throw new Error("DATABASE_URL is not set");
    client = neon(url);
  }
  return client;
}
