"use client";
import { useI18n } from "@/hooks/useI18n";
export default function EmployeeLanguage() {
  const { locale, setLocale } = useI18n(true);
  return <div className="flex justify-end gap-2 mb-3" aria-label="Employee language">
    {([['my', 'မြန်မာ'], ['th', 'ไทย']] as const).map(([code, label]) => <button key={code} type="button" onClick={() => setLocale(code)} className={`px-3 py-2 rounded-lg border ${locale === code ? 'bg-blue-50 text-blue-700' : 'bg-white'}`}>{label}</button>)}
  </div>;
}
