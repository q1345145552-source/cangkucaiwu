import { api } from "@/lib/api";
import type { MakeupDisplayRecord } from "@/lib/makeup-display";

interface ClockRecordPage {
  employees: { id: number; name: string; user_id: number | null }[];
  records: MakeupDisplayRecord[];
  total: number;
  employees_total: number;
}

// Fetch only an explicit date range and (for grids) the visible employee page.
// Finish that slice before rendering: a partial set must never look like absence.
export async function loadClockRecordPages(query: string, current: () => boolean = () => true) {
  const params = new URLSearchParams(query);
  params.set("page_size", "100");
  params.set("page", "1");
  const first = await api.get<ClockRecordPage>(`/clock-in/records?${params}`);
  const records = [...first.records];
  for (let page = 2; records.length < first.total; page++) {
    if (!current()) throw new Error("打卡记录查询已切换");
    params.set("page", String(page));
    const next = await api.get<ClockRecordPage>(`/clock-in/records?${params}`);
    if (!next.records.length) throw new Error("打卡记录已变化，请刷新重试");
    records.push(...next.records);
  }
  return { ...first, records };
}
