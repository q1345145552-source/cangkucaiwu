"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, Bell, Users, Warehouse } from "lucide-react";
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

interface WarehouseCardsProps {
  refreshKey?: number;
  onWarehousesLoaded?: (warehouses: { warehouse_id: number; warehouse_name: string; warehouse_code: string }[]) => void;
  onCreate?: () => void;
  onManage?: (id: number) => void;
  renderOverview?: (summary: { warehouseCount: number; pendingCount: number }) => ReactNode;
}

type CardsState =
  | { kind: "loading" }
  | { kind: "ready"; cards: WarehouseCard[] }
  | { kind: "forbidden" }
  | { kind: "error"; message: string };

const gridClass = "grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3";
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

export default function WarehouseCards({ refreshKey = 0, onWarehousesLoaded, onCreate, onManage, renderOverview }: WarehouseCardsProps) {
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
      onWarehousesLoaded?.(response.data.map(({ warehouse_id, warehouse_name, warehouse_code }) => ({
        warehouse_id, warehouse_name, warehouse_code,
      })));
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
  }, [user?.id, user?.role, loading, attempt, refreshKey, onWarehousesLoaded]);

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
  if (state.cards.length === 0) return user.role === "warehouse_admin" ? (
    <div role="status" className="text-gray-700">
      <p>你名下还没有仓库 请联系平台管理员分配</p>
      <p className="mt-2 text-sm text-gray-600">或者自己新建一个仓库</p>
      <button type="button" onClick={onCreate} className="mt-3 min-h-[44px] rounded-lg border border-gray-300 bg-white px-4 text-sm font-medium text-blue-700 hover:bg-blue-50">新建仓库</button>
    </div>
  ) : <p role="status" className="text-gray-700">你名下还没有仓库 请联系平台管理员分配</p>;

  return (
    <div className={gridClass}>
      {renderOverview?.({ warehouseCount: state.cards.length, pendingCount: state.cards.reduce((total, card) => total + card.todos.total, 0) })}
      {state.cards.map(card => {
        const enterCard = <button type="button" aria-label={`进入${card.warehouse_name}`}
          onClick={() => enterWarehouse(card.warehouse_id)}
          className="flex min-h-[372px] w-full min-w-0 flex-col items-stretch rounded-2xl border border-slate-200 bg-white p-6 text-left text-slate-900 shadow-sm transition-[transform,box-shadow,border-color] duration-200 [@media(hover:hover)_and_(pointer:fine)]:hover:-translate-y-0.5 [@media(hover:hover)_and_(pointer:fine)]:hover:border-blue-300 [@media(hover:hover)_and_(pointer:fine)]:hover:shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 motion-reduce:transform-none motion-reduce:transition-none sm:min-h-[352px]">
          <div className="mb-6 flex items-start gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
              <Warehouse aria-hidden="true" className="h-6 w-6" strokeWidth={1.75} />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <h2 className="break-words text-xl font-bold leading-7 tracking-tight">{card.warehouse_name}</h2>
              {card.warehouse_code && <p className="mt-1 break-all text-sm text-slate-500">{card.warehouse_code}</p>}
            </div>
            {card.todos.total > 0 && <span aria-label={`未处理待办 ${card.todos.total} 条`} className="mt-1 inline-flex min-h-6 min-w-7 shrink-0 items-center justify-center rounded-full bg-red-100 px-2 text-xs font-bold tabular-nums text-red-700">{card.todos.total}</span>}
          </div>
          {card.has_data ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-6 border-t border-slate-100 pt-5">
              <div className="flex min-w-0 flex-col">
                <dt className="order-2 mt-1.5 pl-6 text-sm text-slate-500">今日收入</dt>
                <dd className="order-1 flex items-start gap-2 font-mono text-lg font-semibold tabular-nums text-emerald-700">
                  <ArrowUpRight aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-emerald-500" />
                  <span className="min-w-0"><Amounts amounts={card.income_by_currency} /></span>
                </dd>
              </div>
              <div className="flex min-w-0 flex-col">
                <dt className="order-2 mt-1.5 pl-6 text-sm text-slate-500">今日支出</dt>
                <dd className="order-1 flex items-start gap-2 font-mono text-lg font-semibold tabular-nums text-red-600">
                  <ArrowDownRight aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-red-500" />
                  <span className="min-w-0"><Amounts amounts={card.expense_by_currency} /></span>
                </dd>
              </div>
              <div className="flex min-w-0 flex-col">
                <dt className="order-2 mt-1.5 pl-6 text-sm text-slate-500">待办</dt>
                <dd className="order-1 flex items-start gap-2 font-mono text-xl font-semibold tabular-nums text-amber-700">
                  <Bell aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-amber-500" />
                  {card.todos.total}
                </dd>
              </div>
              <div className="flex min-w-0 flex-col">
                <dt className="order-2 mt-1.5 pl-6 text-sm text-slate-500">出勤</dt>
                <dd className="order-1 flex items-start gap-2 font-mono text-xl font-semibold tabular-nums text-blue-700">
                  <Users aria-hidden="true" className="mt-1 h-4 w-4 shrink-0 text-blue-500" />
                  {card.attendance.actual} / {card.attendance.expected}
                </dd>
                <dd className="order-3 mt-3">
                  <div role="progressbar" aria-label="出勤进度" aria-valuemin={0} aria-valuemax={card.attendance.expected || 1} aria-valuenow={Math.min(card.attendance.actual, card.attendance.expected)} aria-valuetext={`实到 ${card.attendance.actual} / 应到 ${card.attendance.expected}`} className="h-1.5 overflow-hidden rounded-full bg-blue-50">
                    <div className="h-full rounded-full bg-blue-500" style={{ width: `${card.attendance.expected > 0 ? Math.min(100, card.attendance.actual / card.attendance.expected * 100) : 0}%` }} />
                  </div>
                  <p className="mt-1.5 text-xs leading-5 text-slate-500">实到 {card.attendance.actual} / 应到 {card.attendance.expected}</p>
                </dd>
              </div>
            </dl>
          ) : <p className="text-gray-500">暂无数据</p>}
        </button>;
        if (user.role === "warehouse_admin") return <div key={card.warehouse_id} className="relative min-w-0">
          {enterCard}
          <button type="button" aria-label={`管理${card.warehouse_name}`} onClick={event => { event.stopPropagation(); onManage?.(card.warehouse_id); }}
            className="absolute right-5 top-5 z-10 min-h-[44px] rounded-lg border border-gray-300 bg-white px-3 text-sm font-medium text-blue-700 hover:bg-blue-50">管理</button>
        </div>;
        return <div key={card.warehouse_id} className="min-w-0">{enterCard}</div>;
      })}
    </div>
  );
}
