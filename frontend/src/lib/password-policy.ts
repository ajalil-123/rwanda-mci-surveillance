/** Shared by sign-up and password reset (server actions and form hints). */
export const MIN_PASSWORD_LENGTH = 10;
export const MAX_PASSWORD_LENGTH = 200;

/** Returns an error message, or null when the new password is acceptable. */
export function checkNewPassword(password: string, confirm: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (password.length > MAX_PASSWORD_LENGTH) return "Password is too long.";
  if (password !== confirm) return "Passwords do not match.";
  return null;
}
