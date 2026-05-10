"use client";
import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

const PROVIDERS = [
  {
    id: "google",
    label: "Continuer avec Google",
    icon: "🔵",
  },
  {
    id: "github",
    label: "Continuer avec GitHub",
    icon: "🐙",
  },
];

export default function LoginPage() {
  const { status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") router.replace("/");
  }, [status, router]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div
        className="w-full max-w-sm rounded-xl border p-8 space-y-6"
        style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}
      >
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>
            Sip-feed
          </h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Connectez-vous pour synchroniser vos préférences
          </p>
        </div>

        <div className="space-y-3">
          {PROVIDERS.map(({ id, label, icon }) => (
            <button
              key={id}
              onClick={() => signIn(id, { callbackUrl: "/" })}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-sm font-medium transition hover:opacity-80"
              style={{
                backgroundColor: "var(--surface-2)",
                borderColor: "var(--border)",
                color: "var(--text)",
              }}
            >
              <span className="text-lg">{icon}</span>
              {label}
            </button>
          ))}
        </div>

        <p className="text-xs text-center" style={{ color: "var(--text-muted)" }}>
          En vous connectant, vous acceptez que vos préférences soient sauvegardées.
        </p>
      </div>
    </div>
  );
}
