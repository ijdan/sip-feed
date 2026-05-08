import type { Metadata } from "next";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import SessionProvider from "@/components/SessionProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tech News Aggregator",
  description: "Vos news tech, structurées et centralisées",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await getServerSession(authOptions);
  return (
    <html lang="fr">
      <body className="bg-gray-50 text-gray-900">
        <SessionProvider session={session}>
          <header className="border-b bg-white px-6 py-4 flex items-center justify-between">
            <h1 className="text-xl font-bold">Tech News</h1>
            <nav className="flex gap-4 text-sm">
              <a href="/" className="hover:underline">Feed</a>
              <a href="/admin" className="hover:underline">Admin</a>
            </nav>
          </header>
          <main className="max-w-4xl mx-auto px-4 py-8">{children}</main>
        </SessionProvider>
      </body>
    </html>
  );
}
