import "server-only";

interface Mail {
  to: string;
  subject: string;
  text: string;
}

/**
 * Sends email through Resend's HTTP API (https://resend.com) when
 * RESEND_API_KEY is set. Without a key, development prints the message to the
 * server console instead; production refuses, so missing config is noticed.
 */
export async function sendMail({ to, subject, text }: Mail): Promise<void> {
  const apiKey = process.env.RESEND_API_KEY;

  if (!apiKey) {
    if (process.env.NODE_ENV === "production") throw new Error("RESEND_API_KEY is not set");
    console.info(`\n[dev mail] To: ${to}\nSubject: ${subject}\n\n${text}\n`);
    return;
  }

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: process.env.EMAIL_FROM ?? "NHIC MCI Surveillance <onboarding@resend.dev>",
      to: [to],
      subject,
      text,
    }),
  });
  if (!res.ok) throw new Error(`Resend responded ${res.status}: ${await res.text()}`);
}
