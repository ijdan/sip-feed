"use client";
import { useState } from "react";
import useSWR from "swr";

const API = process.env.NEXT_PUBLIC_API_URL;

export default function LogViewer({ token }: { token: string }) {
  const [open, setOpen] = useState(false);

  const { data, isLoading, mutate } = useSWR(
    open ? "collector-report" : null,
    () =>
      fetch(`${API}/admin/report`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json())
  );

  const content: string = data?.content ?? "";
  const generatedAt: string = data?.generated_at ?? "";

  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      <button
        onClick={() => { setOpen(!open); if (!open) mutate(); }}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-50 transition"
      >
        <span className="font-semibold text-lg">📋 Rapport de dernière exécution</span>
        <div className="flex items-center gap-3">
          {open && (
            <button
              onClick={(e) => { e.stopPropagation(); mutate(); }}
              className="text-sm text-blue-500 hover:underline"
            >
              Rafraîchir
            </button>
          )}
          <span className="text-gray-400 text-sm">{open ? "▲" : "▼"}</span>
        </div>
      </button>

      {open && (
        <div className="border-t px-6 py-4">
          {isLoading && <p className="text-sm text-gray-400">Chargement...</p>}
          {!isLoading && !content && (
            <p className="text-sm text-gray-400">Aucun rapport disponible. Lance une collecte depuis l'admin.</p>
          )}
          {!isLoading && content && (
            <div className="space-y-1">
              {generatedAt && (
                <p className="text-xs text-gray-400 mb-3">
                  Généré le {new Date(generatedAt).toLocaleString("fr-FR")}
                </p>
              )}
              <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap text-sm leading-relaxed">
                {content}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
