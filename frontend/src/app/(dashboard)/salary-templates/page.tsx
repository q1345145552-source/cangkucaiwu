"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { DollarSign, Plus, Edit2, Trash2 } from "lucide-react";

const TYPE_LABELS: Record<string, string> = { hourly: "按小时", daily: "按天", monthly: "按月" };

export default function SalaryTemplatesPage() {
  const { toast } = useToast(); const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({ name: "", type: "daily", amount: "", overtime_half_hour_fee: "" });

  useEffect(() => { if (!getToken()) { router.push("/login"); return; } load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>("/salary-templates");
      setRows(r.data || []);
    } catch (err: any) { toast("error", err.message || "加载薪资模板失败"); }
    setLoading(false);
  }

  function openCreate() {
    setEditingId(null);
    setForm({ name: "", type: "daily", amount: "", overtime_half_hour_fee: "" });
    setShowForm(true);
  }

  function openEdit(r: any) {
    setEditingId(r.id);
    setForm({ name: r.name, type: r.type, amount: String(r.amount ?? ""), overtime_half_hour_fee: String(r.overtime_half_hour_fee ?? 0) });
    setShowForm(true);
  }

  async function handleSave() {
    if (!form.name.trim()) { toast("error", "请填写模板名称"); return; }
    const amount = parseFloat(form.amount);
    if (!amount || amount <= 0) { toast("error", "金额必须大于0"); return; }
    const ot = parseFloat(form.overtime_half_hour_fee || "0");
    try {
      if (editingId) {
        await api.put(`/salary-templates/${editingId}`, { ...form, amount, overtime_half_hour_fee: ot });
        toast("success", "薪资模板已更新");
      } else {
        await api.post("/salary-templates", { ...form, amount, overtime_half_hour_fee: ot });
        toast("success", "薪资模板创建成功");
      }
      setShowForm(false);
      load();
    } catch (err: any) { toast("error", err.message || "保存失败"); }
  }

  async function handleDelete(r: any) {
    if (r.usage_count > 0) { toast("error", `有 ${r.usage_count} 个员工在使用该模板，不能删除`); return; }
    if (!confirm(`确定删除模板「${r.name}」吗？`)) return;
    try {
      await api.delete(`/salary-templates/${r.id}`);
      toast("success", "薪资模板已删除");
      load();
    } catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><DollarSign size={24}/>薪资模板</h1>
        <button onClick={openCreate} className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
          <Plus size={16}/> 新建模板
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <DollarSign size={40} className="mx-auto mb-3 text-gray-300"/>
          <p>暂无薪资模板</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left px-3 py-3 font-medium text-gray-500">模板名称</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">类型</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">金额</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">加班半小时费</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">使用人数</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-3 py-3 font-medium">{r.name}</td>
                  <td className="px-3 py-3">{TYPE_LABELS[r.type] || r.type}</td>
                  <td className="px-3 py-3 text-right">{r.amount?.toLocaleString()}</td>
                  <td className="px-3 py-3 text-right">{r.overtime_half_hour_fee ?? 0}</td>
                  <td className="px-3 py-3 text-center">{r.usage_count ?? 0}</td>
                  <td className="px-3 py-3 text-center">
                    <div className="flex items-center justify-center gap-3">
                      <button onClick={() => openEdit(r)} className="text-blue-500 hover:text-blue-700" title="编辑"><Edit2 size={16}/></button>
                      <button onClick={() => handleDelete(r)} className="text-red-400 hover:text-red-600" title="删除"><Trash2 size={16}/></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-2xl w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <DollarSign size={20} /><span className="font-semibold">{editingId ? "编辑模板" : "新建模板"}</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">模板名称</label>
                <input className="form-input py-2.5 w-full" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="如：搬运工按天" />
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">类型</label>
                <select className="form-input py-2.5 w-full" value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}>
                  <option value="hourly">按小时</option>
                  <option value="daily">按天</option>
                  <option value="monthly">按月</option>
                </select>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">金额</label>
                <input type="number" step="0.01" className="form-input py-2.5 w-full" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
                <p className="text-xs text-gray-400 mt-1">按小时和按天填日薪，按月填月薪</p>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">加班半小时费</label>
                <input type="number" step="0.01" className="form-input py-2.5 w-full" value={form.overtime_half_hour_fee} onChange={e => setForm({ ...form, overtime_half_hour_fee: e.target.value })} />
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={handleSave} className="btn-primary text-sm px-6 py-2">保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
