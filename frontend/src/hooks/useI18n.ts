"use client";
import { useState, useEffect, useCallback } from "react";
import zh from "@/i18n/zh.json";
import th from "@/i18n/th.json";

const translations: Record<string, Record<string, string>> = { zh, th };

export type Locale = "zh" | "th";

export function useI18n() {
  const [locale, setLocaleState] = useState<Locale>("zh");

  useEffect(() => {
    const saved = localStorage.getItem("locale") as Locale;
    if (saved && (saved === "zh" || saved === "th")) {
      setLocaleState(saved);
    }
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem("locale", l);
  }, []);

  const t = useCallback(
    (key: string): string => {
      return translations[locale]?.[key] || translations.zh[key] || key;
    },
    [locale]
  );

  const toggleLocale = useCallback(() => {
    setLocale(locale === "zh" ? "th" : "zh");
  }, [locale, setLocale]);

  return { t, locale, setLocale, toggleLocale };
}
