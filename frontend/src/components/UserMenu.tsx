"use client";
import { useSession, signOut } from "next-auth/react";

export default function UserMenu() {
  const { data: session } = useSession();
  if (!session) return null;

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-gray-500 hidden sm:block">{session.user?.email}</span>
      <button
        onClick={() => signOut({ callbackUrl: "/" })}
        className="text-gray-600 hover:text-gray-900 border border-gray-300 rounded px-3 py-1 hover:border-gray-500 transition"
      >
        Déconnexion
      </button>
    </div>
  );
}
