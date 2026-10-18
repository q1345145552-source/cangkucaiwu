"use client";

export interface MakeupRecord {
  is_makeup?: boolean;
  makeup_by?: number | null;
  makeup_by_name?: string;
  makeup_at?: string | null;
  makeup_reason?: string | null;
  makeup_batch_id?: number | null;
}

type Translate = (key: string) => string;

export function MakeupBadge({ t }: { t: Translate }) {
  return <span data-makeup-badge title={t("makeup")} aria-label={t("makeup")} className="inline-flex shrink-0 whitespace-nowrap rounded bg-purple-100 text-purple-700 px-1 text-[10px] font-semibold leading-4">{t("makeup_short")}</span>;
}

export function MakeupRecordDetails({ record, t, locale }: { record?: MakeupRecord; t: Translate; locale: string }) {
  if (!record?.is_makeup) return null;
  const language = locale === "th" ? "th-TH" : locale === "my" ? "my-MM" : "zh-CN";
  const operatedAt = record.makeup_at ? new Date(record.makeup_at).toLocaleString(language, { timeZone: "Asia/Bangkok", hour12: false }) : "-";
  return <div data-makeup-details className="mb-2 text-[11px] text-purple-700 bg-purple-50 rounded p-2 space-y-1 break-words">
    <div className="font-medium">{t("makeup")}</div>
    <div>{t("makeup_by")}：{record.makeup_by_name || (record.makeup_by ? `#${record.makeup_by}` : "-")}</div>
    <div>{t("makeup_at")}：{operatedAt}</div>
    <div>{t("reason")}：{record.makeup_reason || "-"}</div>
    {record.makeup_batch_id != null && <div>{t("makeup_batch")}：#{record.makeup_batch_id}</div>}
  </div>;
}
