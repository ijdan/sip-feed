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
    }),
  ],
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account) {
        let res: Response | null = null;

        if (account.provider === "google" && account.id_token) {
          // Vérification côté backend avec l'id_token Google
          res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/google`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credential: account.id_token }),
          });
        } else {
          // GitHub et futurs providers : endpoint générique
          const p = profile as any;
          res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/session`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: token.email,
              name: p?.name || p?.login || token.name || "",
              avatar: p?.avatar_url || token.picture || "",
              provider: account.provider,
            }),
          });
        }

        if (res?.ok) {
          const data = await res.json();
          token.accessToken = data.access_token;
          token.role = data.role;
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
