import { withAuth } from "next-auth/middleware";

/**
 * Proxy (Next 16's name for middleware) — protects all /dashboard/* routes.
 * Unauthenticated visitors are redirected to /login.
 */
export default withAuth({
  pages: { signIn: "/login" },
});

export const config = {
  matcher: ["/dashboard/:path*"],
};
