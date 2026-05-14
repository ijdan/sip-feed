"use client";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import SourceManager from "@/components/admin/SourceManager";
import AdminSettings from "@/components/admin/AdminSettings";
import LogViewer from "@/components/admin/LogViewer";

export default function AdminPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const role = ((session as unknown) as import("@/lib/types").AppSession)?.role;
  const token = ((session as unknown) as import("@/lib/types").AppSession)?.accessToken;

  if (status === "unauthenticated") {
    router.replace("/login");
    return null;
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
      <SourceManager token={token} />
      <LogViewer token={token} />
    </div>
  );
}
