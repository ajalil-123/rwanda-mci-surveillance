import "server-only";
import { createHash, randomBytes } from "node:crypto";
import { db } from "./db";
import { normalizeEmail } from "./users";

export const RESET_TTL_MINUTES = 30;
/** Minimum gap between reset emails for one account (stops inbox flooding). */
const RESEND_COOLDOWN_SECONDS = 60;

function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

/**
 * Creates a reset token for the account, replacing any earlier one.
 * Returns null when the email is unknown or a link was sent very recently —
 * callers must respond identically either way.
 */
export async function createResetToken(email: string): Promise<{ token: string; email: string } | null> {
  const sql = db();
  const [user] = (await sql`
    SELECT u.id, u.email,
           EXISTS (SELECT 1 FROM password_resets r
                   WHERE r.user_id = u.id
                     AND r.created_at > now() - make_interval(secs => ${RESEND_COOLDOWN_SECONDS})) AS throttled
    FROM users u
    WHERE u.email = ${normalizeEmail(email)}
  `) as { id: number; email: string; throttled: boolean }[];
  if (!user || user.throttled) return null;

  const token = randomBytes(32).toString("base64url");
  await sql.transaction([
    sql`DELETE FROM password_resets WHERE user_id = ${user.id}`,
    sql`INSERT INTO password_resets (token_hash, user_id, expires_at)
        VALUES (${hashToken(token)}, ${user.id}, now() + make_interval(mins => ${RESET_TTL_MINUTES}))`,
  ]);
  return { token, email: user.email };
}

/**
 * Atomically consumes the token and sets the new password (also clearing any
 * lockout). Returns false for unknown, expired or already-used tokens.
 */
export async function consumeResetToken(token: string, passwordHash: string): Promise<boolean> {
  const rows = await db()`
    WITH used AS (
      DELETE FROM password_resets
      WHERE token_hash = ${hashToken(token)} AND expires_at > now()
      RETURNING user_id
    )
    UPDATE users
    SET password_hash = ${passwordHash}, failed_logins = 0, locked_until = NULL
    FROM used
    WHERE users.id = used.user_id
    RETURNING users.id
  `;
  return rows.length === 1;
}
