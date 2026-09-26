import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { AuthShell } from "@/components/auth-shell";
import { SignInForm } from "./sign-in-form";

/**
 * Accept only same-origin destinations to prevent open redirects. NextAuth's
 * proxy sends an absolute URL, so normalise that to a path.
 */
function safeCallbackUrl(raw: string | undefined, host: string | null): string {
  const fallback = "/dashboard";
  if (!raw || !host) return fallback;
  try {
    const url = new URL(raw, `http://${host}`);
    return url.host === host ? `${url.pathname}${url.search}` : fallback;
  } catch {
    return fallback;
  }
}

const NOTICES: Record<string, string> = {
  registered: "Account created. You can sign in now.",
  reset: "Password updated. Sign in with your new password.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const raw = typeof params.callbackUrl === "string" ? params.callbackUrl : undefined;
  const callbackUrl = safeCallbackUrl(raw, (await headers()).get("host"));

  // Already signed in — redirect on the server, before any HTML is sent
  if (await getServerSession(authOptions)) redirect(callbackUrl);

  return (
    <AuthShell
      title="Sign in"
      subtitle="Access the surveillance dashboard with your account."
      footer={
        <>
          No account yet?{" "}
          <Link href="/signup" className="font-medium text-foreground underline-offset-4 hover:underline">
            Create one
          </Link>
        </>
      }
    >
      <SignInForm
        callbackUrl={callbackUrl}
        notice={params.registered ? NOTICES.registered : params.reset ? NOTICES.reset : null}
      />
    </AuthShell>
  );
}
