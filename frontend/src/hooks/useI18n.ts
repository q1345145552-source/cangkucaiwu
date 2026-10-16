"use client";
import { useState, useEffect, useCallback } from "react";
import zh from "@/i18n/zh.json";
import th from "@/i18n/th.json";

// my.json loaded on-demand to avoid SSR circular deps
let _myDict: Record<string, string> | null = null;
const _all: Record<string, Record<string, string>> = { zh, th };

function ensureMy() {
  if (!_myDict) {
    // Synchronous require for dynamic import would fail, so use require in effect
  }
  return _all.my || {};
}

export type Locale = "zh" | "th" | "my";

export function useI18n(employeeView = false) {
  const [locale, setLocaleState] = useState<Locale>(employeeView ? "my" : "zh");
  const [, forceUpdate] = useState(0);

  // Load my.json dynamically；加载完成后强制重渲染，确保缅甸语立即生效
  useEffect(() => {
    import("@/i18n/my.json").then((m: any) => {
      _myDict = m.default || m;
      _all.my = _myDict || {};
      forceUpdate(v => v + 1);
    }).catch(() => {});
  }, []);

  // Role-based default: check on mount
  useEffect(() => {
    const saved = (employeeView ? localStorage.getItem("employee-locale") || localStorage.getItem("locale") : localStorage.getItem("locale")) as Locale | null;
    if (saved && (saved === "th" || saved === "my" || (!employeeView && saved === "zh"))) {
      setLocaleState(saved);
      return;
    }
    if (employeeView) { setLocaleState("my"); return; }
    // If no saved preference, check role from localStorage
    const stored = localStorage.getItem("user");
    if (stored) {
      try {
        const u = JSON.parse(stored);
        if (u.role === "warehouse_labor") {
          setLocaleState("my");
          localStorage.setItem("locale", "my");
        }
      } catch {}
    }
  }, [employeeView]);

  // 全局同步：任一组件切换语言时，所有 useI18n 实例一起更新
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail && (detail.locale === "zh" || detail.locale === "th" || detail.locale === "my")) {
        setLocaleState(detail.locale);
      }
    };
    window.addEventListener(employeeView ? "employee-locale-changed" : "locale-changed", handler);
    return () => window.removeEventListener(employeeView ? "employee-locale-changed" : "locale-changed", handler);
  }, [employeeView]);

  const setLocale = useCallback((l: Locale) => {
    if (employeeView && l === "zh") return;
    setLocaleState(l);
    localStorage.setItem(employeeView ? "employee-locale" : "locale", l);
    window.dispatchEvent(new CustomEvent(employeeView ? "employee-locale-changed" : "locale-changed", { detail: { locale: l } }));
  }, [employeeView]);

  const t = useCallback(
    (key: string): string => {
      return _all[locale]?.[key] || _all.zh[key] || key;
    },
    [locale]
  );

  const toggleLocale = useCallback(() => {
    if (locale === "zh") setLocale("th");
    else if (locale === "th") setLocale("my");
    else setLocale(employeeView ? "th" : "zh");
  }, [locale, setLocale, employeeView]);

  return { t, locale, setLocale, toggleLocale };
}
