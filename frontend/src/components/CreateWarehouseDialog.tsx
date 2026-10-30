"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "@/hooks/useAuth";
import { api, ApiError, setActiveWarehouseId } from "@/lib/api";
import type { AuthUser } from "@/types/auth";

interface CreateWarehouseDialogProps {
  onClose: () => void;
  onCreated: () => void;
}

interface CreatedWarehouse { id: number; message?: string }

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.detail;
    if (typeof detail === "string" && detail.trim() && detail !== "Request failed") return detail;
    if (detail && typeof detail.message === "string") return detail.message;
    if (error.status >= 500) return "创建失败，仓库名称或编码可能已存在，请检查后重试";
    return error.message || "创建失败，请重试";
  }
  return error instanceof Error ? error.message : "创建失败，请重试";
}

export default function CreateWarehouseDialog({ onClose, onCreated }: CreateWarehouseDialogProps) {
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const cleanName = name.trim();
    const cleanCode = code.trim();
    if (!cleanName || !cleanCode) {
      setError("请填写仓库名称和仓库编码");
      return;
    }
    if (!user || user.role !== "warehouse_admin") {
      setError("当前账号无权创建仓库");
      return;
    }
    setBusy(true);
    setError("");
    try {
      // The selection page is not scoped to a warehouse; ensure api.post omits the header.
      setActiveWarehouseId(null);
      const result = await api.post<CreatedWarehouse>("/warehouses", { name: cleanName, code: cleanCode });
      if (!Number.isSafeInteger(result?.id) || result.id <= 0) throw new Error("仓库已提交，但服务没有返回新仓库编号");
      const refreshed: AuthUser = {
        ...user,
        warehouses: [...user.warehouses.filter(item => item.id !== result.id), { id: result.id, name: cleanName, code: cleanCode }],
      };
      // useAuth already listens for this event and updates its in-memory and local user cache.
      window.dispatchEvent(new CustomEvent("auth-user-refreshed", { detail: refreshed }));
      onCreated();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" role="presentation">
    <section role="dialog" aria-modal="true" aria-labelledby="create-warehouse-title" className="w-full max-w-md rounded-xl bg-white p-5 text-gray-900 shadow-xl sm:p-6">
      <div className="mb-5 flex items-start justify-between gap-3">
        <h2 id="create-warehouse-title" className="text-lg font-semibold">新建仓库</h2>
        <button type="button" aria-label="关闭" disabled={busy} onClick={onClose} className="min-h-[44px] min-w-[44px] rounded-lg text-2xl leading-none text-gray-500 hover:bg-gray-100 disabled:opacity-50">×</button>
      </div>
      <form onSubmit={submit}>
        <div className="space-y-4">
          <label className="block text-sm font-medium text-gray-700">仓库名称（必填）
            <input autoFocus required maxLength={100} value={name} onChange={event => setName(event.target.value)} className="mt-1 min-h-[44px] w-full rounded-lg border border-gray-300 px-3 text-base text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder="例如：曼谷一仓" />
          </label>
          <label className="block text-sm font-medium text-gray-700">仓库编码（必填）
            <input required maxLength={50} value={code} onChange={event => setCode(event.target.value)} className="mt-1 min-h-[44px] w-full rounded-lg border border-gray-300 px-3 text-base text-gray-900 uppercase outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder="例如：BKK01" />
          </label>
        </div>
        {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" disabled={busy} onClick={onClose} className="min-h-[44px] rounded-lg border border-gray-300 px-4 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">取消</button>
          <button type="submit" disabled={busy} className="min-h-[44px] rounded-lg bg-blue-600 px-5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-wait disabled:opacity-60">{busy ? "正在创建…" : "创建仓库"}</button>
        </div>
      </form>
    </section>
  </div>;
}
