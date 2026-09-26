import { dropBlankAuthUrls } from "@/lib/env";

/** Runs once when the server starts, before any request is handled. */
export function register(): void {
  dropBlankAuthUrls();
}
