"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { api, ApiError, setActiveWarehouseId } from "@/lib/api";

interface CurrencyAmount {
  currency: string;
  amount: string | number;
}

interface WarehouseCard {
  warehouse_id: number;
  warehouse_name: string;
  warehouse_code: string;
  income_by_currency: CurrencyAmount[];
  expense_by_currency: CurrencyAmount[];
  todos: { total: number };
  attendance: { actual: number; expected: number };
  has_data: boolean;
}

interface CardsResponse {
  data: WarehouseCard[];
}

type CardsState =
  | { kind: "loading" }
  | { kind: "ready"; cards: WarehouseCard[] }
  | { kind: "forbidden" }
  | { kind: "error"; message: string };

const gridClass = "grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3";
const moneyFormat = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function isAmounts(value: unknown): value is CurrencyAmount[] {
  return Array.isArray(value) && value.every(item => item && typeof item.currency === "string"
    && (typeof item.amount === "number" || (typeof item.amount === "string" && item.amount.trim() !== ""))
    && Number.isFinite(Number(item.amount)));
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isCard(value: unknown): value is WarehouseCard {
  if (!value || typeof value !== "object") return false;
  const card = value as WarehouseCard;
  return Number.isSafeInteger(card.warehouse_id) && card.warehouse_id > 0
    && typeof card.warehouse_name === "string" && typeof card.warehouse_code === "string"
    && typeof card.has_data === "boolean"
    && isAmounts(card.income_by_currency) && isAmounts(card.expense_by_currency)
    && isCount(card.todos?.total) && isCount(card.attendance?.actual) && isCount(card.attendance?.expected);
}

function Amounts({ amounts }: { amounts: CurrencyAmount[] }) {
  if (amounts.length === 0) return <span>0</span>;
  return <>{amounts.map(item => (
    <span key={item.currency} className="block break-words tabular-nums">
      {({ THB: "฿", CNY: "¥" } as Record<string, string>)[item.currency] || item.currency}{" "}
      {moneyFormat.format(Number(item.amount))}
    </span>
  ))}</>;
}

export default function WarehouseCards() {
  const { user, loading } = useAuth();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<CardsState>({ kind: "loading" });
  const [owner, setOwner] = useState<number | null>(null);
  const entering = useRef(false);

  useEffect(() => {
    let active = true;
    entering.current = false;
    setState({ kind: "loading" });
    setOwner(user?.id ?? null);
    if (loading || !user) return () => { active = false; };

    api.get<CardsResponse>("/dashboard/warehouse-cards").then(response => {
      if (!active) return;
      if (!response || !Array.isArray(response.data) || !response.data.every(isCard)
          || new Set(response.data.map(card => card.warehouse_id)).size !== response.data.length) {
        throw new Error("仓库数据格式不正确，请重试");
      }
      setState({ kind: "ready", cards: response.data });
    }).catch((error: unknown) => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 403) {
        setState({ kind: "forbidden" });
      } else {
        const message = error instanceof TypeError ? "无法连接服务，请检查网络或稍后重试"
          : error instanceof SyntaxError ? "服务返回内容无法读取，请重试"
          : error instanceof Error ? error.message : "加载失败，请重试";
        setState({ kind: "error", message });
      }
    });
    return () => { active = false; };
  }, [user?.id, user?.role, loading, attempt]);

  function enterWarehouse(id: number) {
    if (entering.current) return;
    entering.current = true;
    setActiveWarehouseId(id);
    window.dispatchEvent(new CustomEvent("warehouse-changed", { detail: { warehouseId: id } }));
    // Re-mount the existing layout so its local switcher state reads the chosen warehouse.
    window.location.assign("/dashboard");
  }

  if (loading || !user || owner !== user.id || state.kind === "loading") {
    return (
      <div role="status" aria-label="仓库加载中" className={gridClass}>
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} aria-hidden="true" className="h-56 animate-pulse rounded-xl border border-gray-200 bg-white p-5">
            <div className="mb-6 h-6 w-2/3 rounded bg-gray-200" />
            <div className="grid grid-cols-2 gap-5">
              {Array.from({ length: 4 }, (_, n) => <div key={n} className="h-12 rounded bg-gray-100" />)}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (state.kind === "forbidden") return <p role="status" className="text-gray-700">当前账号不需要选择仓库</p>;
  if (state.kind === "error") return (
    <div role="alert" className="rounded-xl border border-red-200 bg-white p-5">
      <p className="break-words text-red-700">加载失败：{state.message}</p>
      <button type="button" onClick={() => { setState({ kind: "loading" }); setAttempt(value => value + 1); }}
        className="mt-4 min-h-[44px] rounded-lg bg-blue-600 px-5 text-white hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">重试</button>
    </div>
  );
  if (state.cards.length === 0) return <p role="status" className="text-gray-700">你名下还没有仓库 请联系平台管理员分配</p>;

  return (
    <div className={gridClass}>
      {state.cards.map(card => (
        <button key={card.warehouse_id} type="button" aria-label={`进入${card.warehouse_name}`}
          onClick={() => enterWarehouse(card.warehouse_id)}
          className="min-w-0 rounded-xl border border-gray-200 bg-white p-5 text-left text-gray-900 shadow-sm hover:border-blue-400 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">
          <h2 className="mb-5 break-words text-xl font-bold">{card.warehouse_name}</h2>
          {card.has_data ? (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-5">
              <div><dt className="mb-1 text-sm text-gray-500">今日收入</dt><dd className="text-base font-semibold"><Amounts amounts={card.income_by_currency} /></dd></div>
              <div><dt className="mb-1 text-sm text-gray-500">今日支出</dt><dd className="text-base font-semibold"><Amounts amounts={card.expense_by_currency} /></dd></div>
              <div><dt className="mb-1 text-sm text-gray-500">待办</dt><dd className={`text-lg font-semibold tabular-nums ${card.todos.total > 0 ? "text-orange-700" : "text-gray-900"}`}>{card.todos.total}</dd></div>
              <div><dt className="mb-1 text-sm text-gray-500">出勤</dt><dd className="text-lg font-semibold tabular-nums">{card.attendance.actual} / {card.attendance.expected}</dd></div>
            </dl>
          ) : <p className="text-gray-500">暂无数据</p>}
        </button>
      ))}
    </div>
  );
}
