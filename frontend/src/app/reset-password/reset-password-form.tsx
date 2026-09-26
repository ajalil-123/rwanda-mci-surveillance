"use client";

import { useActionState } from "react";
import { Field, FormAlert } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/ui/password-input";
import { MIN_PASSWORD_LENGTH } from "@/lib/password-policy";
import { resetPassword, type ResetState } from "../forgot-password/actions";

export function ResetPasswordForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState<ResetState, FormData>(resetPassword, {});

  return (
    <form action={action} className="space-y-4">
      {state.error ? <FormAlert>{state.error}</FormAlert> : null}
      <input type="hidden" name="token" value={token} />
      <Field id="password" label={`New password (min. ${MIN_PASSWORD_LENGTH} characters)`}>
        <PasswordInput
          id="password"
          name="password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          autoComplete="new-password"
          className="h-10 text-sm"
        />
      </Field>
      <Field id="confirm" label="Confirm new password">
        <PasswordInput
          id="confirm"
          name="confirm"
          required
          minLength={MIN_PASSWORD_LENGTH}
          autoComplete="new-password"
          className="h-10 text-sm"
        />
      </Field>
      <Button type="submit" size="lg" className="w-full" disabled={pending}>
        {pending ? "Saving…" : "Set new password"}
      </Button>
    </form>
  );
}
