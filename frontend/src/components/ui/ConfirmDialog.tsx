"use client";
import { AlertTriangle } from "lucide-react";

export default function ConfirmDialog({
  open,
  title = "确认操作",
  message = "确定要删除吗？",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title?: string;
  message?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/40 z-[9998] flex items-center justify-center">
      <div className="bg-white rounded-xl p-6 w-96 shadow-xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
            <AlertTriangle size={20} className="text-red-500" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-800">{title}</h3>
            <p className="text-sm text-gray-500">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-3">
          <button onClick={onCancel} className="px-4 py-2 border rounded-lg text-sm hover:bg-gray-50">取消</button>
          <button onClick={onConfirm} className="px-4 py-2 bg-red-500 text-white rounded-lg text-sm hover:bg-red-600">确认删除</button>
        </div>
      </div>
    </div>
  );
}
