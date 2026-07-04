"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { getToken } from "@/lib/api";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { TrendingUp, TrendingDown, AlertTriangle, Package, ShoppingCart } from "lucide-react";

interface Stats {
  total_recharge_month: number;
  total_incoming_month: number;
  unmatched_count: number;
  pending_market_review: number;
  pending_group_orders: number;
}

const dummyStats: Stats = {
  total_recharge_month: 0,
  total_incoming_month: 0,
  unmatched_count: 0,
  pending_market_review: 0,
  pending_group_orders: 0,
};

export default function DashboardPage() {
  const { user } = useAuth();
  const { t } = useI18n();
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) router.push("/login");
  }, [router]);

  return (
    <DashboardLayout>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-800">{t("dashboard")}</h1>
        <p className="text-sm text-gray-500 mt-1">
          {user?.display_name} · {user?.warehouse_name || t("overview")}
        </p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-8">
        <StatCard
          icon={<TrendingUp className="h-6 w-6 text-green-600" />}
          label={t("total_recharge")}
          value={`THB ${dummyStats.total_recharge_month.toLocaleString()}`}
          color="bg-green-50"
        />
        <StatCard
          icon={<TrendingDown className="h-6 w-6 text-blue-600" />}
          label={t("total_incoming")}
          value={`THB ${dummyStats.total_incoming_month.toLocaleString()}`}
          color="bg-blue-50"
        />
        <StatCard
          icon={<AlertTriangle className="h-6 w-6 text-orange-600" />}
          label={t("unmatched_count")}
          value={String(dummyStats.unmatched_count)}
          color="bg-orange-50"
        />
        <StatCard
          icon={<Package className="h-6 w-6 text-purple-600" />}
          label={t("pending_review")}
          value={String(dummyStats.pending_market_review)}
          color="bg-purple-50"
        />
        <StatCard
          icon={<ShoppingCart className="h-6 w-6 text-teal-600" />}
          label={t("pending_group")}
          value={String(dummyStats.pending_group_orders)}
          color="bg-teal-50"
        />
      </div>

      {/* Quick actions */}
      <div className="rounded-xl bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">{t("warehouse_summary")}</h2>
        <p className="text-gray-400 text-sm">
          各仓库数据将在 Phase 2 接入后端 API 后动态展示
        </p>
      </div>
    </DashboardLayout>
  );
}

function StatCard({ icon, label, value, color }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className={`rounded-xl ${color} p-4 shadow-sm`}>
      <div className="flex items-center justify-between mb-2">{icon}</div>
      <div className="text-2xl font-bold text-gray-800">{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  );
}
