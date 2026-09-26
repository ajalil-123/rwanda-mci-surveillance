import Link from "next/link";
import { AuthShell, FormAlert } from "@/components/auth-shell";
import { ResetPasswordForm } from "./reset-password-form";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { token } = await searchParams;

  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Reset links work once and expire after 30 minutes."
      footer={
        <Link href="/forgot-password" className="font-medium text-foreground underline-offset-4 hover:underline">
          Request a new link
        </Link>
      }
    >
      {typeof token === "string" && token ? (
        <ResetPasswordForm token={token} />
      ) : (
        <FormAlert>This reset link is invalid. Request a new one.</FormAlert>
      )}
    </AuthShell>
  );
}
