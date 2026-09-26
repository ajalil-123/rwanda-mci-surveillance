"use server";

import { hashPassword } from "@/server/password";
import { consumeResetToken, createResetToken, RESET_TTL_MINUTES } from "@/server/password-reset";
import { sendMail } from "@/server/mail";
import { checkNewPassword } from "@/lib/password-policy";
import { appBaseUrl } from "@/lib/env";
import { redirect } from "next/navigation";

export interface ForgotState {
  sent?: boolean;
  error?: string;
}

export async function requestPasswordReset(_prev: ForgotState, form: FormData): Promise<ForgotState> {
  const email = String(form.get("email") ?? "").trim();
  if (!email) return { error: "Enter your email address." };

  // Links are built from configuration (NEXTAUTH_URL, or Vercel's production URL),
  // never from the request's Host header, so an attacker can't make the email
  // point at their own site.
  const baseUrl = appBaseUrl();
  if (!baseUrl) {
    console.error("requestPasswordReset: no app URL (set NEXTAUTH_URL outside Vercel)");
    return { error: "Password reset is not configured. Contact the administrator." };
  }

  try {
    const reset = await createResetToken(email);
    if (reset) {
      const link = `${baseUrl}/reset-password?token=${reset.token}`;
      await sendMail({
        to: reset.email,
        subject: "Reset your NHIC MCI Surveillance password",
        text: [
          "Someone asked to reset the password for this account.",
          "",
          `Open this link within ${RESET_TTL_MINUTES} minutes to choose a new password:`,
          link,
          "",
          "If you did not ask for this, ignore this email. Your password stays the same.",
        ].join("\n"),
      });
    }
  } catch (error) {
    console.error("requestPasswordReset failed", error);
    return { error: "Could not send the reset email. Please try again later." };
  }

  // Same answer whether or not the account exists
  return { sent: true };
}

export interface ResetState {
  error?: string;
}

export async function resetPassword(_prev: ResetState, form: FormData): Promise<ResetState> {
  const token = String(form.get("token") ?? "");
  const password = String(form.get("password") ?? "");
  const invalid = checkNewPassword(password, String(form.get("confirm") ?? ""));
  if (!token) return { error: "This reset link is invalid. Request a new one." };
  if (invalid) return { error: invalid };

  let ok: boolean;
  try {
    ok = await consumeResetToken(token, await hashPassword(password));
  } catch (error) {
    console.error("resetPassword failed", error);
    return { error: "Could not reset the password. Please try again." };
  }
  if (!ok) return { error: "This reset link is invalid or has expired. Request a new one." };

  redirect("/login?reset=1");
}
