import { ApiError } from '@/lib/api';
export const RECEIPT_PHOTO_MAX_BYTES = 10 * 1024 * 1024;
export function receiptPhotoError(file: File | null): string | null {
  if (!file) return '请上传到货照片';
  if (!file.size) return '图片上传失败，请重试：照片为空文件';
  if (file.size > RECEIPT_PHOTO_MAX_BYTES) return '图片上传失败，请重试：到货照片不能超过10MB';
  if (!file.type.startsWith('image/')) return '图片上传失败，请重试：请选择有效图片';
  return null;
}
function message(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(message).join('；');
  if (detail && typeof detail === 'object') {
    const row = detail as Record<string, unknown>;
    return message(row.message || row.msg || row.detail || '收货接口返回异常，请重试');
  }
  return '收货接口返回异常，请重试';
}
export async function readReceiptResponse(response: Response): Promise<any> {
  const text = await response.text();
  let result: any;
  try { result = JSON.parse(text); }
  catch { throw new ApiError(response.ok ? 502 : response.status, '图片上传或收货请求失败，请重试；原请求编号已保留，结果待核对'); }
  if (!response.ok) {
    const detail = result?.detail;
    throw new ApiError(response.status, detail && typeof detail === 'object' && !Array.isArray(detail) ? detail : message(detail));
  }
  if (!result?.receipt_event_id || !['received', 'partially_received'].includes(result.receipt_status)) {
    throw new ApiError(502, '收货结果不完整，请沿用原请求重试核对，未显示保存成功');
  }
  return result;
}
