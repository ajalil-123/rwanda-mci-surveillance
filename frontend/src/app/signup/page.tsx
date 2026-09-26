import Link from "next/link";
import { redirect } from "next/navigation";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { AuthShell } from "@/components/auth-shell";
import { SignUpForm } from "./sign-up-form";

export default async function SignUpPage() {
  if (await getServerSession(authOptions)) redirect("/dashboard");

  return (
    <AuthShell
      title="Create account"
      subtitle="Register with your work email to access the surveillance dashboard."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <SignUpForm />
    </AuthShell>
  );
}
