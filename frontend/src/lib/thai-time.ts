/** Thailand timezone utilities for frontend display */

const THAI_OFFSET = 7 * 60; // UTC+7 in minutes

/** Convert any date to Thailand time string */
export function toThaiTime(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleString("zh-CN", { timeZone: "Asia/Bangkok" });
}

export function toThaiDate(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleDateString("zh-CN", { timeZone: "Asia/Bangkok" });
}

export function toThaiTimeOnly(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleTimeString("zh-CN", { timeZone: "Asia/Bangkok", hour: "2-digit", minute: "2-digit" });
}

/** Get current Thailand time as ISO string (for display) */
export function thaiNow(): Date {
  const now = new Date();
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
  return new Date(utcMs + THAI_OFFSET * 60000);
}

/** Format Thai time as HH:MM:SS */
export function formatThaiTime(date?: Date): string {
  const d = date || thaiNow();
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  const s = String(d.getSeconds()).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

/** Format Thai date as YYYY年MM月DD日 */
export function formatThaiDate(date?: Date): string {
  const d = date || thaiNow();
  return `${d.getFullYear()}年${String(d.getMonth() + 1).padStart(2, "0")}月${String(d.getDate()).padStart(2, "0")}日`;
}
