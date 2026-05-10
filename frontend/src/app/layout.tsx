import type { Metadata } from "next";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import SessionProvider from "@/components/SessionProvider";
import BurgerMenu from "@/components/BurgerMenu";
import Controls from "@/components/Controls";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sip-feed",
  description: "Vos news tech, structurées et centralisées",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await getServerSession(authOptions);
  return (
    <html lang="fr" suppressHydrationWarning>
      <body style={{ backgroundColor: "var(--bg)", color: "var(--text)" }}>
        <SessionProvider session={session}>
          <header
            style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
            className="border-b px-6 py-3 flex items-center justify-between"
          >
            <h1 className="text-xl font-bold">Sip-feed</h1>
            <div className="flex items-center gap-2">
              <Controls />
              <BurgerMenu />
            </div>
          </header>
          <main className="max-w-5xl mx-auto px-4 py-6">{children}</main>
        </SessionProvider>
      </body>
    </html>
  );
}
