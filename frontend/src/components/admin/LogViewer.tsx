"use client";
import { useState } from "react";
import useSWR from "swr";

const API = process.env.NEXT_PUBLIC_API_URL;

const SEVERITY_STYLES: Record<string, string> = {
  ERROR:    "text-red-600 bg-red-50",
  WARNING:  "text-yellow-700 bg-yellow-50",
  INFO:     "text-gray-700 bg-white",
  DEFAULT:  "text-gray-500 bg-white",
};

const SEVERITY_PREFIX: Record<string, string> = {
  ERROR:   "✕",
  WARNING: "⚠",
  INFO:    "·",
  DEFAULT: "·",
};

interface LogEntry {
  timestamp: string;
  severity: string;
  message: string;
}

function formatTime(ts: string) {
  if (!ts) return "";
  return new Date(ts).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function LogViewer({ token }: { token: string }) {
  const [open, setOpen] = useState(false);

  const { data, isLoading, mutate } = useSWR(
    open ? "collector-logs" : null,
    () =>
      fetch(`${API}/admin/logs`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json())
  );

  const logs: LogEntry[] = data?.logs ?? [];

  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      <button
        onClick={() => { setOpen(!open); if (!open) mutate(); }}
        className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-50 transition"
      >
        <span className="font-semibold text-lg">Logs du collector</span>
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
        <div className="border-t">
          {isLoading && (
            <p className="text-sm text-gray-400 px-6 py-4">Chargement des logs...</p>
          )}
          {!isLoading && logs.length === 0 && (
            <p className="text-sm text-gray-400 px-6 py-4">Aucun log disponible.</p>
          )}
          {!isLoading && logs.length > 0 && (
            <div className="font-mono text-xs max-h-96 overflow-y-auto divide-y">
              {logs.map((log, i) => {
                const sev = SEVERITY_STYLES[log.severity] ?? SEVERITY_STYLES.DEFAULT;
                const prefix = SEVERITY_PREFIX[log.severity] ?? "·";
                return (
                  <div key={i} className={`flex gap-3 px-4 py-1 ${sev}`}>
                    <span className="shrink-0 text-gray-400 w-20">{formatTime(log.timestamp)}</span>
                    <span className="shrink-0 w-3">{prefix}</span>
                    <span className="break-all">{log.message}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
