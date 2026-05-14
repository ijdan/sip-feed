"use client";
import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";

export interface UserSettings {
  theme: "light" | "dark";
  columns: 1 | 2 | 3;
  font_size: "sm" | "md" | "lg";
  excluded_categories: string[];
  excluded_sources: string[];
  hide_read: boolean;
  default_lang: "fr" | "en";
}

const DEFAULTS: UserSettings = {
  theme: "light",
  columns: 1,
  font_size: "md",
  excluded_categories: [],
  excluded_sources: [],
  hide_read: false,
  default_lang: "fr",
};

const API = process.env.NEXT_PUBLIC_API_URL;

async function fetchSettings(token: string): Promise<UserSettings | null> {
  try {
    const res = await fetch(`${API}/users/me/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.ok ? res.json() : null;
  } catch { return null; }
}

async function pushSettings(token: string, s: UserSettings): Promise<void> {
  try {
    await fetch(`${API}/users/me/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(s),
    });
  } catch { /* silent */ }
}

function applyToDOM(s: UserSettings) {
  document.documentElement.classList.toggle("dark", s.theme === "dark");
  document.documentElement.classList.remove("font-size-sm", "font-size-md", "font-size-lg");
  document.documentElement.classList.add(`font-size-${s.font_size}`);
}

function saveLocal(s: UserSettings) {
  localStorage.setItem("user-settings", JSON.stringify(s));
  localStorage.setItem("theme", s.theme);
  localStorage.setItem("feed-columns", String(s.columns));
  localStorage.setItem("font-size", s.font_size);
  localStorage.setItem("feed-excluded-sources", JSON.stringify(s.excluded_sources));
  localStorage.setItem("feed-excluded-categories", JSON.stringify(s.excluded_categories));
  localStorage.setItem("feed-hide-read", String(s.hide_read));
  localStorage.setItem("settings-default-lang", s.default_lang);
}

function loadLocal(): UserSettings {
  try {
    const raw = localStorage.getItem("user-settings");
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch { /* */ }
  return {
    theme: (localStorage.getItem("theme") as "light" | "dark") || DEFAULTS.theme,
    columns: Number(localStorage.getItem("feed-columns") || DEFAULTS.columns) as 1 | 2 | 3,
    font_size: (localStorage.getItem("font-size") as "sm" | "md" | "lg") || DEFAULTS.font_size,
    excluded_categories: JSON.parse(localStorage.getItem("feed-excluded-categories") || "[]"),
    excluded_sources: JSON.parse(localStorage.getItem("feed-excluded-sources") || "[]"),
    hide_read: localStorage.getItem("feed-hide-read") === "true",
    default_lang: (localStorage.getItem("settings-default-lang") as "fr" | "en") || DEFAULTS.default_lang,
  };
}

export function useSettings() {
  const { data: session } = useSession();
  const token = (session as any)?.accessToken as string | undefined;
  const [settings, setSettings] = useState<UserSettings>(DEFAULTS);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const local = loadLocal();
    setSettings(local);
    applyToDOM(local);
    setLoaded(true);

    if (token) {
      fetchSettings(token).then((remote) => {
        if (!remote) return;
        setSettings(remote);
        applyToDOM(remote);
        saveLocal(remote);
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const save = useCallback((next: UserSettings) => {
    setSettings(next);
    applyToDOM(next);
    saveLocal(next);
    if (token) pushSettings(token, next);
  }, [token]);

  const update = useCallback((partial: Partial<UserSettings>) => {
    setSettings(prev => {
      const next = { ...prev, ...partial };
      applyToDOM(next);
      saveLocal(next);
      if (token) pushSettings(token, next);
      return next;
    });
  }, [token]);

  return { settings, save, update, loaded };
}
