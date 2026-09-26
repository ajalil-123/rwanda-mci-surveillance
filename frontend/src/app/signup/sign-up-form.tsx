"use client";

import { useActionState } from "react";
import { Field, FormAlert } from "@/components/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { MIN_PASSWORD_LENGTH } from "@/lib/password-policy";
import { signUp, type SignUpState } from "./actions";

export function SignUpForm() {
  const [state, action, pending] = useActionState<SignUpState, FormData>(signUp, {});

  return (
    <form action={action} className="space-y-4">
      {state.error ? <FormAlert>{state.error}</FormAlert> : null}

      <Field id="name" label="Full name">
        <Input id="name" name="name" autoComplete="name" defaultValue={state.name} className="h-10 text-sm" />
      </Field>
      <Field id="email" label="Email">
        <Input
          id="email"
          name="email"
          type="email"
          required
          autoComplete="email"
          defaultValue={state.email}
          className="h-10 text-sm"
        />
      </Field>
      <Field id="password" label={`Password (min. ${MIN_PASSWORD_LENGTH} characters)`}>
        <PasswordInput
          id="password"
          name="password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          autoComplete="new-password"
          className="h-10 text-sm"
        />
      </Field>
      <Field id="confirm" label="Confirm password">
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
        {pending ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
