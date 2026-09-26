"use server";

import { redirect } from "next/navigation";
import { hashPassword } from "@/server/password";
import { createUser } from "@/server/users";
import { checkNewPassword } from "@/lib/password-policy";

export interface SignUpState {
  error?: string;
  email?: string;
  name?: string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function signUp(_prev: SignUpState, form: FormData): Promise<SignUpState> {
  const email = String(form.get("email") ?? "").trim();
  const name = String(form.get("name") ?? "").trim();
  const password = String(form.get("password") ?? "");
  const confirm = String(form.get("confirm") ?? "");
  const keep = { email, name };

  if (!EMAIL_RE.test(email) || email.length > 254) return { ...keep, error: "Enter a valid email address." };
  const invalid = checkNewPassword(password, confirm);
  if (invalid) return { ...keep, error: invalid };

  let created: boolean;
  try {
    created = await createUser(email, name.slice(0, 100) || null, await hashPassword(password));
  } catch (error) {
    console.error("signUp failed", error);
    return { ...keep, error: "Could not create the account. Please try again." };
  }
  if (!created) return { ...keep, error: "An account with this email already exists. Sign in instead." };

  redirect("/login?registered=1");
}
