"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { Field, FormAlert } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";

export function SignInForm({ callbackUrl, notice }: { callbackUrl: string; notice: string | null }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);

    const result = await signIn("credentials", {
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
      redirect: false,
    });

    if (result?.ok && !result.error) {
      router.replace(callbackUrl);
      router.refresh();
      return;
    }
    setPending(false);
    // One message for every failure, so the form never reveals which emails exist
    setError("Incorrect email or password. After 5 failed attempts the account is locked for 15 minutes.");
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {notice && !error ? <FormAlert tone="success">{notice}</FormAlert> : null}
      {error ? <FormAlert>{error}</FormAlert> : null}

      <Field id="email" label="Email">
        <Input id="email" name="email" type="email" required autoComplete="email" className="h-10 text-sm" />
      </Field>
      <Field id="password" label="Password">
        <PasswordInput
          id="password"
          name="password"
          required
          autoComplete="current-password"
          className="h-10 text-sm"
        />
      </Field>

      <div className="flex justify-end">
        <Link href="/forgot-password" className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
          Forgot password?
        </Link>
      </div>

      <Button type="submit" size="lg" className="w-full" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
