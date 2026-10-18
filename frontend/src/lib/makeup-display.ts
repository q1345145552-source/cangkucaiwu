import type { MakeupRecord } from "@/components/MakeupDisplay";

export interface MakeupDisplayRecord extends MakeupRecord {
  employee_id: number;
  clock_date: string;
  session: number;
}

// Display metadata only: never infer makeup from missing photos, time, actor or batch.
export function makeupRecordsByDay(records: MakeupDisplayRecord[]): Record<string, MakeupDisplayRecord[]> {
  const days: Record<string, MakeupDisplayRecord[]> = {};
  for (const record of records) {
    if (!record.is_makeup || record.employee_id == null) continue;
    const key = `${record.clock_date}_${record.employee_id}`;
    (days[key] ||= []).push(record);
  }
  return days;
}

export function attachMakeupDetails<T extends { session: number }>(sessions: T[], records: MakeupDisplayRecord[], employeeId: number, date: string): (T & MakeupRecord)[] {
  return sessions.map(session => {
    const record = records.find(r => r.employee_id === employeeId && r.clock_date === date && r.session === session.session);
    if (!record?.is_makeup) return session;
    return { ...session, is_makeup: true, makeup_by: record.makeup_by, makeup_by_name: record.makeup_by_name,
      makeup_at: record.makeup_at, makeup_reason: record.makeup_reason, makeup_batch_id: record.makeup_batch_id };
  });
}
