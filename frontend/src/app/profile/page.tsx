"use client";
import { useState, useEffect } from "react";
import { useSession, signOut } from "next-auth/react";
import { useRouter } from "next/navigation";
import { usePreferences } from "@/lib/usePreferences";

const API = process.env.NEXT_PUBLIC_API_URL;

interface Profile {
  internal_id: string;
  email: string;
  name: string;
  avatar: string;
  role: string;
  created_at: string;
}

export default function ProfilePage() {
  const { data: session, status } = useSession();
  const token = (session as any)?.accessToken as string | undefined;
  const router = useRouter();
  const { favorites, readingList, readArticles } = usePreferences();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [editName, setEditName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    fetch(`${API}/users/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(data => { setProfile(data); setNameInput(data?.name ?? ""); })
      .finally(() => setLoading(false));
  }, [token]);

  const deleteAccount = async () => {
    if (!token) return;
    setDeleting(true);
    await fetch(`${API}/users/me`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    await signOut({ callbackUrl: "/" });
  };

  const saveName = async () => {
    if (!token || !nameInput.trim()) return;
    setSaving(true);
    const res = await fetch(`${API}/users/me`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ name: nameInput.trim() }),
    });
    if (res.ok) {
      const updated = await res.json();
      setProfile(updated);
      setEditName(false);
    }
    setSaving(false);
  };

  if (status === "unauthenticated") {
    router.replace("/login");
    return null;
  }

  if (loading) return <p className="mt-20 text-center" style={{ color: "var(--text-muted)" }}>Chargement…</p>;

  if (!profile) return <p className="mt-20 text-center" style={{ color: "var(--text-muted)" }}>Profil introuvable.</p>;

  const joinedDate = new Date(profile.created_at).toLocaleDateString("fr-FR", {
    day: "numeric", month: "long", year: "numeric",
  });

  return (
    <div className="max-w-lg mx-auto mt-8 space-y-6">

      {/* Carte profil */}
      <div className="rounded-xl border p-6 space-y-4"
        style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>

        {/* Avatar + nom */}
        <div className="flex items-center gap-4">
          {profile.avatar ? (
            <img src={profile.avatar} alt="" className="w-16 h-16 rounded-full object-cover" />
          ) : (
            <div className="w-16 h-16 rounded-full flex items-center justify-center text-2xl font-bold"
              style={{ backgroundColor: "var(--surface-2)", color: "var(--text)" }}>
              {profile.email[0].toUpperCase()}
            </div>
          )}
          <div className="flex-1 min-w-0">
            {editName ? (
              <div className="flex items-center gap-2">
                <input
                  value={nameInput}
                  onChange={e => setNameInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && saveName()}
                  className="flex-1 rounded border px-2 py-1 text-sm"
                  style={{ backgroundColor: "var(--surface-2)", borderColor: "var(--border)", color: "var(--text)" }}
                  autoFocus
                />
                <button onClick={saveName} disabled={saving}
                  className="text-sm px-3 py-1 rounded font-medium disabled:opacity-50"
                  style={{ backgroundColor: "var(--text)", color: "var(--bg)" }}>
                  {saving ? "…" : "OK"}
                </button>
                <button onClick={() => setEditName(false)} className="text-sm"
                  style={{ color: "var(--text-muted)" }}>Annuler</button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="font-semibold text-lg truncate" style={{ color: "var(--text)" }}>
                  {profile.name || "—"}
                </span>
                <button onClick={() => setEditName(true)}
                  className="text-xs opacity-50 hover:opacity-100 transition"
                  style={{ color: "var(--text-muted)" }}>✏️</button>
              </div>
            )}
            <p className="text-sm truncate" style={{ color: "var(--text-muted)" }}>{profile.email}</p>
          </div>
        </div>

        {/* Infos */}
        <div className="space-y-2 text-sm pt-2 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="flex justify-between">
            <span style={{ color: "var(--text-muted)" }}>ID interne</span>
            <code className="text-xs" style={{ color: "var(--text-muted)" }}>{profile.internal_id}</code>
          </div>
          <div className="flex justify-between">
            <span style={{ color: "var(--text-muted)" }}>Rôle</span>
            <span style={{ color: "var(--text)" }}>{profile.role}</span>
          </div>
          <div className="flex justify-between">
            <span style={{ color: "var(--text-muted)" }}>Membre depuis</span>
            <span style={{ color: "var(--text)" }}>{joinedDate}</span>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="rounded-xl border p-6" style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
        <h2 className="font-semibold mb-4" style={{ color: "var(--text)" }}>Activité</h2>
        <div className="grid grid-cols-3 gap-4 text-center">
          {[
            { icon: "⭐", count: favorites.size, label: "Favoris" },
            { icon: "👓", count: readingList.size, label: "À lire" },
            { icon: "✓", count: readArticles.size, label: "Lus" },
          ].map(({ icon, count, label }) => (
            <div key={label} className="space-y-1">
              <div className="text-2xl">{icon}</div>
              <div className="text-2xl font-bold" style={{ color: "var(--text)" }}>{count}</div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Suppression du compte */}
      <div className="rounded-xl border p-6 space-y-3"
        style={{ backgroundColor: "var(--surface)", borderColor: "var(--border)" }}>
        <h2 className="font-semibold" style={{ color: "var(--text)" }}>Compte</h2>
        {!deleteConfirm ? (
          <button onClick={() => setDeleteConfirm(true)}
            className="px-4 py-2 rounded border text-sm font-medium transition"
            style={{ borderColor: "#ef4444", color: "#ef4444", backgroundColor: "var(--surface)" }}>
            Supprimer mon compte
          </button>
        ) : (
          <div className="space-y-3 p-4 rounded-lg border" style={{ borderColor: "#ef4444" }}>
            <p className="text-sm font-medium" style={{ color: "#ef4444" }}>
              ⚠️ Cette action est irréversible. Toutes vos données seront supprimées.
            </p>
            <div className="flex gap-3">
              <button onClick={deleteAccount} disabled={deleting}
                className="px-4 py-2 rounded text-sm font-medium text-white disabled:opacity-50"
                style={{ backgroundColor: "#ef4444" }}>
                {deleting ? "Suppression…" : "Confirmer"}
              </button>
              <button onClick={() => setDeleteConfirm(false)}
                className="px-4 py-2 rounded text-sm" style={{ color: "var(--text-muted)" }}>
                Annuler
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
