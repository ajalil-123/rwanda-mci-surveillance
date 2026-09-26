import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import { verifyAgainstDummy, verifyPassword } from "@/server/password";
import { findUserByEmail, recordFailedLogin, resetFailedLogins } from "@/server/users";

/**
 * NextAuth configuration — email + password, JWT sessions.
 *
 * - Accounts live in the Neon `users` table (scrypt password hashes)
 * - JWT strategy: the session is a signed, encrypted cookie (NEXTAUTH_SECRET)
 * - 5 failed attempts lock an account for 15 minutes
 */

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: "Email",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = credentials?.email ?? "";
        const password = credentials?.password ?? "";
        if (!email || !password) return null;

        const user = await findUserByEmail(email);
        if (!user) {
          await verifyAgainstDummy(password);
          return null;
        }
        if (user.locked) return null;

        if (!(await verifyPassword(password, user.password_hash))) {
          await recordFailedLogin(user.id);
          return null;
        }
        await resetFailedLogins(user.id);
        return { id: String(user.id), email: user.email, name: user.name };
      },
    }),
  ],
  session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
  pages: {
    signIn: "/login",
    error: "/login",
  },
};
