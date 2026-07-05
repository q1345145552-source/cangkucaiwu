"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { getToken, api } from "@/lib/api";
import { TrendingUp, TrendingDown, AlertTriangle, Package, ShoppingCart, FileText, Receipt, Tag } from "lucide-react";

interface Stats {
  total_recharge_month: number;
  total_incoming_month: number;
  unmatched_count: number;
  pending_market_review: number;
  pending_group_orders: number;
  pending_expense_fund_reviews: number;
  pending_reimbursements: number;
}

interface PendingTask {
  type: string;
  description: string;
  link: string;
  id: number;
}

const PENDING_TYPE_CONFIG: Record<string, { icon: React.ReactNode; color: string; badge: string }> = {
  expense_fund: { icon: <FileText className="h-4 w-4" />, color: "text-red-600 bg-red-50", badge: "备用金" },
  reimbursement: { icon: <Receipt className="h-4 w-4" />, color: "text-orange-600 bg-orange-50", badge: "报销" },
  market: { icon: <Tag className="h-4 w-4" />, color: "text-blue-600 bg-blue-50", badge: "商品" },
};

export default function DashboardPage() {
  const { user } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [tasks, setTasks] = useState<PendingTask[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    loadData();
  }, [router]);

  async function loadData() {
    try {
      const [s, tk] = await Promise.all([
        api.get<Stats>("/dashboard/stats"),
        api.get<{ data: PendingTask[] }>("/dashboard/pending-tasks"),
      ]);
      setStats(s);
      setTasks(tk.data || []);
    } catch (e) {
      console.error("Dashboard load error:", e);
    }
    setLoading(false);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">加载中...</div>
    );
  }

  const s = stats;

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800">{t("dashboard")}</h1>
        <p className="text-sm text-gray-500 mt-1">
          {user?.display_name} · {user?.warehouse_name || t("overview")}
        </p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-8">
        <StatCard icon={<TrendingUp className="h-6 w-6 text-green-600" />} label={t("total_recharge")} value={`THB ${(s?.total_recharge_month || 0).toLocaleString()}`} color="bg-green-50" />
        <StatCard icon={<TrendingDown className="h-6 w-6 text-blue-600" />} label={t("total_incoming")} value={`THB ${(s?.total_incoming_month || 0).toLocaleString()}`} color="bg-blue-50" />
        <StatCard icon={<AlertTriangle className="h-6 w-6 text-orange-600" />} label={t("unmatched_count")} value={String(s?.unmatched_count || 0)} color="bg-orange-50" />
        <StatCard icon={<Package className="h-6 w-6 text-purple-600" />} label="待审核商品" value={String(s?.pending_market_review || 0)} color="bg-purple-50" />
        <StatCard icon={<ShoppingCart className="h-6 w-6 text-teal-600" />} label={t("pending_group")} value={String(s?.pending_group_orders || 0)} color="bg-teal-50" />
      </div>

      {/* Pending tasks */}
      <div className="rounded-xl bg-white p-6 shadow-sm mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-700">待办提醒</h2>
          <span className="text-sm text-gray-400">{tasks.length} 项待处理</span>
        </div>

        {tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-gray-400">
            <svg className="w-12 h-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>暂无待办事项</span>
          </div>
        ) : (
          <div className="space-y-2">
            {/* Group by type */}
            {(["expense_fund", "reimbursement", "market"] as const).map((type) => {
              const typeTasks = tasks.filter((t) => t.type === type);
              if (typeTasks.length === 0) return null;
              const cfg = PENDING_TYPE_CONFIG[type];
              return (
                <div key={type} className="mb-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
                      {cfg.icon}
                      {cfg.badge}
                    </span>
                    <span className="text-xs text-gray-400">{typeTasks.length} 项</span>
                  </div>
                  {typeTasks.map((task) => (
                    <div
                      key={task.id}
                      onClick={() => router.push(task.link)}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors text-sm text-gray-700"
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-50 shrink-0" />
                      <span>{task.description}</span>
                      <svg className="w-3 h-3 text-gray-300 ml-auto shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Warehouse summary */}
      <div className="rounded-xl bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">{t("warehouse_summary")}</h2>
        <p className="text-gray-400 text-sm">各仓库数据将在后续版本中动态展示</p>
      </div>
    </>
  );
}

function StatCard({ icon, label, value, color }: {
  icon: React.ReactNode; label: string; value: string; color: string;
}) {
  return (
    <div className={`rounded-xl ${color} p-4 shadow-sm`}>
      <div className="flex items-center justify-between mb-2">{icon}</div>
      <div className="text-2xl font-bold text-gray-800">{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  );
}
