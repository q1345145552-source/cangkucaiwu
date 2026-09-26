"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { MinusCircle, Plus, Trash2 } from "lucide-react";

function todayStr(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}

export default function EmployeeDeductionsPage() {
  const { toast } = useToast(); const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [employees, setEmployees] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ employee_id: 0, amount: "", deduction_date: todayStr(), reason: "" });
  const [filterEmp, setFilterEmp] = useState(0);
  const [filterPeriod, setFilterPeriod] = useState("");

  useEffect(() => { if (!getToken()) { router.push("/login"); return; } load(); loadRefs(); }, []);
  useEffect(() => { load(); }, [filterEmp, filterPeriod]);

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterEmp) params.set("employee_id", String(filterEmp));
      if (filterPeriod) params.set("period", filterPeriod);
      const r = await api.get<any>(`/employee-deductions?${params.toString()}`);
      setRows(r.data || []);
    } catch (err: any) { toast("error", err.message || "加载扣款记录失败"); }
    setLoading(false);
  }

  async function loadRefs() {
    try {
      const er = await api.get<any>("/employees?page_size=200&active_only=true");
      setEmployees(er.data || []);
    } catch {}
  }

  async function handleCreate() {
    if (!form.employee_id) { toast("error", "请选择员工"); return; }
    const amt = parseFloat(form.amount);
    if (!amt || amt <= 0) { toast("error", "请填写扣款金额"); return; }
    if (!form.reason.trim()) { toast("error", "请填写扣款原因"); return; }
    try {
      await api.post("/employee-deductions", { ...form, amount: amt });
      toast("success", "扣款记录已创建");
      setShowForm(false);
      setForm({ employee_id: 0, amount: "", deduction_date: todayStr(), reason: "" });
      load();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  async function handleDelete(id: number) {
    if (!confirm("确定删除这条扣款记录吗？")) return;
    try {
      await api.delete(`/employee-deductions/${id}`);
      toast("success", "已删除");
      load();
    } catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  const fmtPeriod = (period: string, half: string) => `${period} ${half === "second_half" ? "下半月" : "上半月"}`;

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><MinusCircle size={24}/>员工扣款</h1>
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
          <Plus size={16}/> 记一笔扣款
        </button>
      </div>

      {/* 筛选 */}
      <div className="flex gap-2 items-center mb-3 flex-wrap">
        <select value={filterEmp || ""} onChange={e => setFilterEmp(+e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm bg-white min-w-[160px]">
          <option value="">全部员工</option>
          {employees.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </select>
        <input type="month" value={filterPeriod} onChange={e => setFilterPeriod(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm bg-white" />
        {(filterEmp || filterPeriod) && (
          <button onClick={() => { setFilterEmp(0); setFilterPeriod(""); }}
            className="text-sm text-gray-500 hover:text-gray-700">重置</button>
        )}
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <MinusCircle size={40} className="mx-auto mb-3 text-gray-300"/>
          <p>暂无扣款记录</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left px-3 py-3 font-medium text-gray-500">员工</th>
                <th className="text-right px-3 py-3 font-medium text-gray-500">扣款金额</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">扣款日期</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">所属周期</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">扣款原因</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">操作人</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-3 py-3 font-medium">{r.employee_name}</td>
                  <td className="px-3 py-3 text-right font-bold text-red-600">{r.amount?.toLocaleString()}</td>
                  <td className="px-3 py-3">{r.deduction_date}</td>
                  <td className="px-3 py-3">{fmtPeriod(r.period, r.half)}</td>
                  <td className="px-3 py-3 text-gray-500 max-w-48 truncate" title={r.reason}>{r.reason}</td>
                  <td className="px-3 py-3">{r.operator_name || "-"}</td>
                  <td className="px-3 py-3 text-center">
                    <button onClick={() => handleDelete(r.id)} className="text-red-400 hover:text-red-600" title="删除">
                      <Trash2 size={16}/>
                    </button>
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
              <MinusCircle size={20} /><span className="font-semibold">记一笔扣款</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">员工</label>
                <select className="form-input py-2.5 w-full" value={form.employee_id || ""} onChange={e => setForm({ ...form, employee_id: +e.target.value })}>
                  <option value="">请选择员工</option>
                  {employees.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">金额</label>
                <input type="number" step="0.01" className="form-input py-2.5 w-full" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">扣款日期</label>
                <input type="date" className="form-input py-2.5 w-full" value={form.deduction_date} onChange={e => setForm({ ...form, deduction_date: e.target.value })} />
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">扣款原因 <span className="text-red-400">*</span></label>
                <input className="form-input py-2.5 w-full" value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} placeholder="如：违规操作罚款" />
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={handleCreate} className="btn-primary text-sm px-6 py-2">提交</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
