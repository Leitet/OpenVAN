import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getModels, getSettings, saveSettings } from "@shared/api";
import type { Settings } from "@shared/types";
import { useI18n, type Lang } from "../i18n";

// Shared state for every Settings category. Lives above the category sub-tabs so
// switching category keeps the loaded settings + fetched models, and a save in one
// panel is reflected everywhere.

const ASST_OVERRIDE_KEY = "openvan.assistantLangOverride";

interface SettingsValue {
  settings: Settings | null;
  offlineModels: string[];
  onlineModels: string[];
  loadingModels: boolean;
  saving: boolean;
  saved: boolean;
  patch: (p: Parameters<typeof saveSettings>[0]) => Promise<void>;
  refreshModels: () => Promise<void>;
  lang: Lang;
  asstOverride: boolean;
  changeAppLang: (l: Lang) => void;
  changeAsstLang: (v: string) => void;
}

const Ctx = createContext<SettingsValue | null>(null);

export function useSettings(): SettingsValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSettings must be used within <SettingsProvider>");
  return v;
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const { lang, setLang } = useI18n();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [offlineModels, setOfflineModels] = useState<string[]>([]);
  const [onlineModels, setOnlineModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [asstOverride, setAsstOverride] = useState(
    () => localStorage.getItem(ASST_OVERRIDE_KEY) === "1",
  );

  const refreshModels = async () => {
    setLoadingModels(true);
    try {
      const [off, on] = await Promise.all([getModels("offline"), getModels("online")]);
      setOfflineModels(off);
      setOnlineModels(on);
    } finally {
      setLoadingModels(false);
    }
  };

  useEffect(() => {
    (async () => {
      setSettings(await getSettings());
      await refreshModels();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const patch = async (p: Parameters<typeof saveSettings>[0]) => {
    setSaving(true);
    setSaved(false);
    try {
      setSettings(await saveSettings(p));
      await refreshModels(); // provider/URL/key changes affect reachable models
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  // Once loaded, sync the assistant (model) language to the app language unless the
  // user has explicitly chosen a different one.
  const synced = useRef(false);
  useEffect(() => {
    if (settings && !synced.current) {
      synced.current = true;
      if (!asstOverride && settings.language !== lang) patch({ language: lang });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings]);

  const changeAppLang = (l: Lang) => {
    setLang(l);
    if (!asstOverride) patch({ language: l });
  };

  const changeAsstLang = (v: string) => {
    if (v === "auto") {
      setAsstOverride(false);
      localStorage.removeItem(ASST_OVERRIDE_KEY);
      patch({ language: lang });
    } else {
      setAsstOverride(true);
      localStorage.setItem(ASST_OVERRIDE_KEY, "1");
      patch({ language: v as Lang });
    }
  };

  return (
    <Ctx.Provider
      value={{
        settings,
        offlineModels,
        onlineModels,
        loadingModels,
        saving,
        saved,
        patch,
        refreshModels,
        lang,
        asstOverride,
        changeAppLang,
        changeAsstLang,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}
