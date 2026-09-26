import "server-only";
import { db } from "./db";

export const MAX_FAILED_LOGINS = 5;
export const LOCKOUT_MINUTES = 15;

export interface UserRow {
  id: number;
  email: string;
  name: string | null;
  password_hash: string;
  locked: boolean;
}

export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export async function findUserByEmail(email: string): Promise<UserRow | null> {
  const rows = (await db()`
    SELECT id, email, name, password_hash, COALESCE(locked_until > now(), false) AS locked
    FROM users
    WHERE email = ${normalizeEmail(email)}
  `) as UserRow[];
  return rows[0] ?? null;
}

/** Returns false when the email is already registered. */
export async function createUser(email: string, name: string | null, passwordHash: string): Promise<boolean> {
  const rows = await db()`
    INSERT INTO users (email, name, password_hash)
    VALUES (${normalizeEmail(email)}, ${name}, ${passwordHash})
    ON CONFLICT (email) DO NOTHING
    RETURNING id
  `;
  return rows.length === 1;
}

/** Counts a failed attempt; locks the account once the limit is reached. */
export async function recordFailedLogin(id: number): Promise<void> {
  await db()`
    UPDATE users
    SET failed_logins = failed_logins + 1,
        locked_until  = CASE WHEN failed_logins + 1 >= ${MAX_FAILED_LOGINS}
                             THEN now() + make_interval(mins => ${LOCKOUT_MINUTES})
                             ELSE locked_until END
    WHERE id = ${id}
  `;
}

export async function resetFailedLogins(id: number): Promise<void> {
  await db()`UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ${id} AND failed_logins > 0`;
}
