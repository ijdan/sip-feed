"use client";
import { useSession } from "next-auth/react";
import SourceManager from "@/components/admin/SourceManager";
import AdminSettings from "@/components/admin/AdminSettings";
import LogViewer from "@/components/admin/LogViewer";

export default function AdminPage() {
  const { data: session } = useSession();
  const role = (session as any)?.role;
  const token = (session as any)?.accessToken;

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
