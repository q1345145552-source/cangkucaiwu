"use client";
import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from "react";
import { CheckCircle, XCircle, X } from "lucide-react";

interface Toast {
  id: number;
  type: "success" | "error";
  message: string;
}

const ToastContext = createContext({
  toast: (_type: "success" | "error", _msg: string) => {},
});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((type: "success" | "error", message: string) => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, type, message }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3000);
  }, []);

  // 监听全局 toast 事件（来自 api.ts 的 showGlobalToast）
  useEffect(() => {
    const handler = (e: Event) => {
      const { type, message } = (e as CustomEvent).detail;
      addToast(type, message);
    };
    window.addEventListener("global-toast", handler);
    return () => window.removeEventListener("global-toast", handler);
  }, [addToast]);

  const remove = (id: number) => setToasts(prev => prev.filter(t => t.id !== id));

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
        {toasts.map(t => (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm animate-slide-in max-w-sm ${
              t.type === "success" ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"
            }`}
          >
            {t.type === "success" ? <CheckCircle size={18} /> : <XCircle size={18} />}
            <span className="flex-1">{t.message}</span>
            <button onClick={() => remove(t.id)} className="hover:opacity-70"><X size={14} /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
