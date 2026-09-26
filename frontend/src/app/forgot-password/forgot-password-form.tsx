"use client";

import { useActionState } from "react";
import { Field, FormAlert } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { requestPasswordReset, type ForgotState } from "./actions";

export function ForgotPasswordForm({ devHint }: { devHint: boolean }) {
  const [state, action, pending] = useActionState<ForgotState, FormData>(requestPasswordReset, {});

  if (state.sent) {
    return (
      <FormAlert tone="success">
        If an account exists for that email, a reset link is on its way. It expires in 30 minutes.
        {devHint ? " (Development: no email service is set up, so the link is printed in the terminal running npm run dev.)" : null}
      </FormAlert>
    );
  }

  return (
    <form action={action} className="space-y-4">
      {state.error ? <FormAlert>{state.error}</FormAlert> : null}
      <Field id="email" label="Email">
        <Input id="email" name="email" type="email" required autoComplete="email" className="h-10 text-sm" />
      </Field>
      <Button type="submit" size="lg" className="w-full" disabled={pending}>
        {pending ? "Sending…" : "Send reset link"}
      </Button>
    </form>
  );
}
