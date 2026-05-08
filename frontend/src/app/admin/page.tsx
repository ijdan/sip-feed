"use client";
import { useSession } from "next-auth/react";
import SourceManager from "@/components/admin/SourceManager";

export default function AdminPage() {
  const { data: session } = useSession();
  const role = (session as any)?.role;

  if (role !== "admin") {
    return <p className="mt-20 text-center text-gray-500">Accès réservé aux administrateurs.</p>;
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Gestion des sources</h2>
      <SourceManager token={(session as any).accessToken} />
    </div>
  );
}
