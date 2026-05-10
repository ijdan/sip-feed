"use client";
import { useState, useEffect, useRef } from "react";
import { useSession, signIn, signOut } from "next-auth/react";
import Link from "next/link";

export default function BurgerMenu() {
  const [open, setOpen] = useState(false);
  const { data: session, status } = useSession();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        title="Menu"
        className="w-9 h-9 flex items-center justify-center rounded-md transition text-lg"
        style={{ color: "var(--text)", backgroundColor: open ? "var(--surface-2)" : "transparent" }}
      >
        ☰
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-2 w-56 rounded-lg border shadow-lg z-50 py-1"
          style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
        >
          <Link href="/" onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-4 py-2.5 text-sm transition hover:opacity-70"
            style={{ color: "var(--text)" }}>
            📰 Feed
          </Link>
          {(session as any)?.role === "admin" && (
            <Link href="/admin" onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-4 py-2.5 text-sm transition hover:opacity-70"
              style={{ color: "var(--text)" }}>
              ⚙️ Admin
            </Link>
          )}

          <div className="my-1 border-t" style={{ borderColor: "var(--border)" }} />

          {status === "authenticated" && (
            <>
              <Link href="/profile" onClick={() => setOpen(false)}
                className="flex items-center gap-2 px-4 py-2.5 text-sm transition hover:opacity-70"
                style={{ color: "var(--text)" }}>
                👤 Profil
              </Link>
              {session?.user?.email && (
                <div className="px-4 py-1.5 text-xs truncate" style={{ color: "var(--text-muted)" }}>
                  {session.user.email}
                </div>
              )}
              <button
                onClick={() => { signOut({ callbackUrl: "/" }); setOpen(false); }}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-sm transition hover:opacity-70 text-left"
                style={{ color: "var(--text)" }}
              >
                🚪 Déconnexion
              </button>
            </>
          )}

          {status === "unauthenticated" && (
            <>
              <button
                onClick={() => { signIn("google"); setOpen(false); }}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-sm transition hover:opacity-70 text-left"
                style={{ color: "var(--text)" }}
              >
                🔵 Google
              </button>
              <button
                onClick={() => { signIn("github"); setOpen(false); }}
                className="w-full flex items-center gap-2 px-4 py-2.5 text-sm transition hover:opacity-70 text-left"
                style={{ color: "var(--text)" }}
              >
                🐙 GitHub
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
