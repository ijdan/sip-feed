import { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import GithubProvider from "next-auth/providers/github";

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    GithubProvider({
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
      authorization: { params: { scope: "read:user user:email" } },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        let res: Response;

        try {
          if (account.provider === "google" && account.id_token) {
            // Vérification côté backend avec l'id_token Google
            res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/google`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ credential: account.id_token }),
            });
          } else if (account.provider === "github" && account.access_token) {
            // Vérification côté backend avec l'access token opaque GitHub.
            res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/github`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                provider: account.provider,
                access_token: account.access_token,
              }),
            });
          } else {
            token.authError = "unsupported_provider";
            return token;
          }

          if (!res.ok) {
            token.authError = `backend_${res.status}`;
            return token;
          }

          const data = await res.json();
          if (!data.access_token || !data.role) {
            token.authError = "invalid_backend_response";
            return token;
          }

          token.accessToken = data.access_token;
          token.role = data.role;
          delete token.authError;
        } catch {
          token.authError = "backend_unreachable";
        }
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string;
      session.role = token.role as string;
      return session;
    },
  },
};
