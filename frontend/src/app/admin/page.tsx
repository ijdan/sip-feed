"use client";
import { useSession, signIn } from "next-auth/react";
import SourceManager from "@/components/admin/SourceManager";
import AdminSettings from "@/components/admin/AdminSettings";
import LogViewer from "@/components/admin/LogViewer";

export default function AdminPage() {
  const { data: session, status } = useSession();
  const role = (session as any)?.role;
  const token = (session as any)?.accessToken;

  if (status === "unauthenticated") {
    return (
      <div className="flex flex-col items-center gap-4 mt-20">
        <p className="text-gray-500">Connectez-vous pour accéder à l'administration.</p>
        <button
          onClick={() => signIn("google")}
          className="bg-gray-900 text-white px-6 py-2 rounded hover:bg-gray-700 transition"
        >
          Se connecter avec Google
        </button>
      </div>
    );
  }

  if (status === "loading") {
    return <p className="mt-20 text-center text-gray-400">Chargement...</p>;
  }

  if (role !== "admin") {
    return <p className="mt-20 text-center text-gray-500">Accès réservé aux administrateurs.</p>;
  }

  return (
    <div className="space-y-8">
      <h2 className="text-2xl font-bold">Administration</h2>
      <AdminSettings token={token} />
      <LogViewer token={token} />
      <SourceManager token={token} />
    </div>
  );
}
