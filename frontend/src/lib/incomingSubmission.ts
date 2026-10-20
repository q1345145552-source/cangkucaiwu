export interface IncomingPayload {
  customer_id?: number | null;
  received_date: string; amount: number; currency: string; account_id: number;
  payer_name: string; payment_method: string; remark: string;
}
export interface IncomingOperation {
  requestKey: string; payload: IncomingPayload; savedId: number | null; screenshotPending: boolean;
}
export interface SavedIncoming { id: number; has_screenshot: boolean; request_key?: string }
export interface IncomingIO {
  create: (payload: IncomingPayload & { request_key: string }) => Promise<SavedIncoming>;
  lookup: (key: string) => Promise<SavedIncoming | null>;
  upload: (id: number, file: File) => Promise<unknown>;
  remember: (operation: IncomingOperation) => void;
}

export async function submitIncoming(operation: IncomingOperation, file: File | null, io: IncomingIO) {
  let current = { ...operation };
  io.remember(current); // 请求发出前保存；刷新、断网重试继续用同一请求号。
  if (current.savedId === null) {
    try {
      const saved = await io.create({ ...current.payload, request_key: current.requestKey });
      current.savedId = saved.id;
      if (saved.has_screenshot) current.screenshotPending = false;
    } catch (error) {
      let recovered: SavedIncoming | null = null;
      let checked = false;
      try { recovered = await io.lookup(current.requestKey); checked = true; } catch { /* 保留原请求，待恢复后继续查询。 */ }
      if (checked && !recovered && [400, 422].includes(Number((error as { status?: number })?.status))) {
        return { status: "rejected" as const, error };
      }
      if (!recovered) return { status: "unconfirmed" as const, error };
      current.savedId = recovered.id;
      if (recovered.has_screenshot) current.screenshotPending = false;
    }
    io.remember(current); // 先记住已入账编号，再开始上传。附件失败不能重新创建到账。
  }
  if (file) {
    try { await io.upload(current.savedId!, file); }
    catch (error) { return { status: "screenshot_failed" as const, id: current.savedId!, error }; }
    current.screenshotPending = false;
    io.remember(current);
  }
  if (current.screenshotPending) return { status: "screenshot_needed" as const, id: current.savedId! };
  return { status: "saved" as const, id: current.savedId! };
}
