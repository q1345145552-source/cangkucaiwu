"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { fmtMoney } from "@/lib/currency";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { Calendar, Play, Download, Eye, X, ChevronRight, FileText } from "lucide-react";

export default function PaymentPlansPage() {
  const { toast } = useToast(); const router = useRouter();
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [bills, setBills] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ plan_name: "", planned_date: "", bill_ids: [] as number[], remark: "", save_as_template: false, template_name: "" });
  const [selectedBills, setSelectedBills] = useState<number[]>([]);
  const [showDetail, setShowDetail] = useState<any>(null);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadBills(); loadTemplates(); loadTimeline(); }, []);

  async function load() {
    setLoading(true);
    try { const r = await api.get<any>("/payable/plans"); setPlans(r.data); }
    catch (err) { console.error("加载失败:", err); }
    setLoading(false);
  }
  async function loadBills() { try { const r = await api.get<any>("/payable?page_size=200"); setBills(r.data); } catch {} }
  async function loadTemplates() { try { const r = await api.get<any>("/payable/plan-templates"); setTemplates(r.data); } catch {} }
  async function loadTimeline() { try { const r = await api.get<any>("/payable/timeline"); setTimeline(r.data); } catch {} }

  function toggleBill(id: number) {
    setSelectedBills(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  }

  function applyTemplate(tmpl: any) {
    setSelectedBills(tmpl.bill_ids || []);
    setForm({ ...form, template_name: tmpl.name, save_as_template: false });
    toast("success", `已加载模板: ${tmpl.name}`);
  }

  async function handleCreate() {
    try {
      await api.post("/payable/plans", { ...form, bill_ids: selectedBills });
      toast("success", form.save_as_template ? "创建成功，已保存为模板" : "创建成功");
      setShowForm(false); setSelectedBills([]); setForm({ plan_name: "", planned_date: "", bill_ids: [], remark: "", save_as_template: false, template_name: "" });
      load(); loadTemplates();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  async function handleExecute(plan: any) {
    if (!confirm(`确认执行计划"${plan.plan_name}"？\n执行后关联账单将自动标记为已付款。`)) return;
    try {
      await api.put(`/payable/plans/${plan.id}/execute`, {});
      toast("success", "计划执行成功，关联账单已付款");
      load(); loadBills();
    } catch (err: any) { toast("error", err.message || "执行失败"); }
  }

  async function handleDeleteTemplate(id: number) {
    if (!confirm("确认删除该模板？")) return;
    try { await api.delete(`/payable/plan-templates/${id}`); toast("success", "模板已删除"); loadTemplates(); }
    catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  async function handleExport(planId?: number) {
    try {
      const url = planId
        ? `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/payable/plans/export?plan_id=${planId}`
        : `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/payable/plans/export`;
      const res = await fetch(url, { headers: { "Authorization": `Bearer ${getToken()}` } });
      const blob = await res.blob();
      const a = document.createElement("a"); a.href = window.URL.createObjectURL(blob);
      a.download = "payment_plans.xlsx"; a.click();
      toast("success", "导出成功");
    } catch { toast("error", "导出失败"); }
  }

  async function handleViewDetail(planId: number) {
    try {
      const r = await api.get<any>(`/payable/plans/${planId}/detail`);
      setShowDetail(r);
    } catch { toast("error", "加载详情失败"); }
  }

  async function handleUploadAttachment(planId: number, file: File) {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/payable/plans/${planId}/upload-attachment`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: fd,
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || "上传失败"); }
      toast("success", "附件上传成功");
      load();
    } catch (err: any) { toast("error", err.message || "上传失败"); }
  }

  function handleViewAttachment(path: string) {
    const url = `/${path}`;
    if (/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(path)) {
      setPreviewImage(url);
      setPreviewError(false);
    } else {
      window.open(url, "_blank");
    }
  }

  const timelineColors = ["bg-blue-500", "bg-indigo-500", "bg-purple-500", "bg-gray-500"];

  return (
    <>
      <h1 className="page-title mb-5">付款计划管理</h1>

      {/* 资金流出时间轴 */}
      <div className="card mb-5">
        <div className="flex items-center gap-2 mb-3"><Calendar size={18} className="text-blue-600" /><span className="font-semibold text-sm">未来四周资金流出预测</span></div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {timeline.map((w: any, i: number) => (
            <div key={i} className={`${timelineColors[i]} text-white rounded-lg p-3`}>
              <div className="text-xs opacity-80">{w.label}</div>
              <div className="text-xs opacity-60 mt-0.5">{w.start} ~ {w.end}</div>
              <div className="font-bold text-lg mt-2">{fmtMoney(w.total)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 操作栏 */}
      <div className="flex items-center gap-3 mb-4">
        <button onClick={() => setShowForm(true)} className="btn-primary">新建计划</button>
        <button onClick={() => handleExport()} className="btn-secondary flex items-center gap-1"><Download size={16} />导出全部</button>
      </div>

      {/* 模板管理（如果有模板） */}
      {templates.length > 0 && (
        <div className="card mb-4 p-4">
          <div className="text-sm font-semibold text-gray-500 mb-2">计划模板</div>
          <div className="flex flex-wrap gap-2">
            {templates.map((t: any) => (
              <div key={t.id} className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-1.5 text-sm">
                <span className="text-blue-700 cursor-pointer hover:underline" onClick={() => applyTemplate(t)}>{t.name}</span>
                <span className="text-xs text-gray-400">({(t.bill_ids || []).length}条)</span>
                <button onClick={() => handleDeleteTemplate(t.id)} className="text-red-400 hover:text-red-600"><X size={14} /></button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 计划列表 */}
      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={[
        { key: "plan_name", label: "计划名称", render: (v: any, row: any) => <button onClick={() => handleViewDetail(row.id)} className="text-blue-600 hover:underline text-left">{v}</button> },
        { key: "planned_date", label: "计划日期", render: (v: any) => v?.slice(0, 10) },
        { key: "total_amount", label: "金额", align: "right", render: (v: any, row: any) => fmtMoney(v, row.currency) },
        { key: "status", label: "状态", render: (v: any) => {
          const map: Record<string, string> = { pending: "待执行", executed: "已执行", cancelled: "已取消" };
          const colors: Record<string, string> = { pending: "bg-yellow-100 text-yellow-700", executed: "bg-green-100 text-green-700", cancelled: "bg-gray-100 text-gray-500" };
          return <span className={`px-2 py-1 rounded text-xs font-medium ${colors[v] || ""}`}>{map[v] || v}</span>;
        }},
        { key: "bill_ids", label: "账单数", render: (v: any) => (v || []).length },
        { key: "bill_attachment", label: "附件", render: (v: any, row: any) => (
          <div className="flex items-center gap-1.5">
            {v ? (
              <button onClick={() => handleViewAttachment(v)} className="text-blue-600 hover:text-blue-800 text-sm">查看</button>
            ) : (
              <span className="text-gray-400">-</span>
            )}
            <label className="text-blue-500 hover:text-blue-700 text-xs cursor-pointer" title={v ? "更换附件" : "上传附件"}>
              <input type="file" className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) handleUploadAttachment(row.id, f); }} />
              {v ? "换" : "上传"}
            </label>
          </div>
        )},
        { key: "id", label: "操作", render: (_: any, row: any) => (
          <div className="flex items-center gap-1">
            {row.status === "pending" && <button onClick={() => handleExecute(row)} className="btn-primary btn-xs flex items-center gap-0.5"><Play size={12} />执行</button>}
            <button onClick={() => handleViewDetail(row.id)} className="btn-secondary btn-xs">详情</button>
            <button onClick={() => handleExport(row.id)} className="btn-secondary btn-xs"><Download size={12} /></button>
          </div>
        )},
      ]} data={plans} total={plans.length} page={1} pageSize={100} onPageChange={() => {}} />}

      {/* 新建计划弹窗 */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[85vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Calendar size={22} />
              <div className="flex-1"><h2 className="text-lg font-semibold">新建付款计划</h2></div>
              <button onClick={() => setShowForm(false)} className="text-blue-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>
            <div className="p-6 space-y-4">
              <div className="form-grid">
                <div className="form-group"><label className="form-label">计划名称</label><input className="form-input" value={form.plan_name} onChange={e => setForm({ ...form, plan_name: e.target.value })} placeholder="如：7月第一周付款" /></div>
                <div className="form-group"><label className="form-label">计划日期</label><input type="date" className="form-input" value={form.planned_date} onChange={e => setForm({ ...form, planned_date: e.target.value })} /></div>
              </div>

              {/* 模板选择 */}
              {templates.length > 0 && (
                <div className="form-group">
                  <label className="form-label">从模板加载</label>
                  <select className="form-input" value="" onChange={e => { if (e.target.value) { const t = templates.find(x => x.id === +e.target.value); if (t) applyTemplate(t); } }}>
                    <option value="">不使用模板</option>
                    {templates.map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </div>
              )}

              {/* 存为模板 */}
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.save_as_template} onChange={e => setForm({ ...form, save_as_template: e.target.checked })} className="w-4 h-4" />
                <span className="text-sm text-gray-600">将此计划存为模板</span>
              </label>
              {form.save_as_template && (
                <div className="form-group"><label className="form-label">模板名称</label><input className="form-input" value={form.template_name} onChange={e => setForm({ ...form, template_name: e.target.value })} placeholder="留空则使用计划名称" /></div>
              )}

              <div className="border-t pt-3">
                <div className="text-sm font-medium mb-2">选择待付账单</div>
                <div className="max-h-[300px] overflow-auto space-y-1">
                  {bills.filter((b: any) => b.status !== "paid").map((b: any) => (
                    <div key={b.id} className="flex items-center gap-3 py-1.5 px-2 rounded hover:bg-gray-50">
                      <input type="checkbox" checked={selectedBills.includes(b.id)} onChange={() => toggleBill(b.id)} className="w-4 h-4" />
                      <span className="text-sm flex-1">{b.supplier_name} - {b.bill_number}</span>
                      <span className="text-xs text-gray-500">{fmtMoney(b.amount, b.currency)}</span>
                      <span className="text-xs bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded">{b.status}</span>
                    </div>
                  ))}
                  {bills.filter((b: any) => b.status !== "paid").length === 0 && (
                    <div className="text-center text-gray-400 py-8">暂无待付账单</div>
                  )}
                </div>
                <div className="text-sm text-blue-600 mt-3 pt-3 border-t">
                  已选 {selectedBills.length} 条，合计 {fmtMoney(bills.filter((b: any) => selectedBills.includes(b.id)).reduce((s: number, b: any) => s + (b.amount - (b.paid_amount || 0)), 0))}
                </div>
              </div>
            </div>
            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handleCreate} className="btn-primary min-w-[80px]">创建计划</button>
            </div>
          </div>
        </div>
      )}

      {/* 计划详情弹窗 */}
      {showDetail && (
        <div className="modal-overlay" onClick={() => setShowDetail(null)}>
          <div className="bg-white rounded-xl w-full max-w-2xl max-h-[85vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-indigo-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <FileText size={22} />
              <div className="flex-1">
                <h2 className="text-lg font-semibold">{showDetail.plan.plan_name}</h2>
                <div className="text-xs text-indigo-100 mt-0.5">
                  计划日期：{showDetail.plan.planned_date?.slice(0, 10)} · 总金额：{fmtMoney(showDetail.plan.total_amount, showDetail.plan.currency)}
                </div>
              </div>
              <button onClick={() => setShowDetail(null)} className="text-indigo-200 hover:text-white"><span className="text-xl leading-none">&times;</span></button>
            </div>
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm text-gray-500">关联账单 · 共 {showDetail.bill_count} 条</span>
                <span className={`px-2 py-1 rounded text-xs font-medium ${showDetail.plan.status === "pending" ? "bg-yellow-100 text-yellow-700" : showDetail.plan.status === "executed" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                  {showDetail.plan.status === "pending" ? "待执行" : showDetail.plan.status === "executed" ? "已执行" : showDetail.plan.status}
                </span>
              </div>
              {showDetail.bills.length === 0 ? (
                <div className="text-center text-gray-400 py-8">暂无关联账单</div>
              ) : (
                <table className="w-full text-sm">
                  <thead><tr className="bg-gray-50">
                    <th className="text-left p-2">供应商</th><th className="text-left p-2">账单编号</th><th className="text-right p-2">金额</th><th className="text-left p-2">到期日</th><th className="text-left p-2">状态</th>
                  </tr></thead>
                  <tbody>
                    {showDetail.bills.map((b: any) => (
                      <tr key={b.id} className="border-t hover:bg-gray-50">
                        <td className="p-2">{b.supplier_name}</td>
                        <td className="p-2">{b.bill_number}</td>
                        <td className="p-2 text-right">{fmtMoney(b.amount, b.currency)}</td>
                        <td className="p-2">{b.due_date?.slice(0, 10)}</td>
                        <td className="p-2">
                          <span className={`px-1.5 py-0.5 rounded text-xs ${b.status === "paid" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>
                            {b.status === "paid" ? "已付" : b.status === "pending" ? "待付" : b.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 附件大图预览 */}
      {previewImage && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[70] p-4" onClick={() => { setPreviewImage(null); setPreviewError(false); }}>
          <div onClick={e => e.stopPropagation()}>
            {previewError ? (
              <div className="text-white text-lg px-6 py-4">图片打不开</div>
            ) : (
              <img src={previewImage} alt="附件" className="max-w-full max-h-[90vh] rounded-lg object-contain" onError={() => setPreviewError(true)} />
            )}
          </div>
        </div>
      )}

      {/* 执行确认弹窗（简化版，直接用 confirm，不需要额外弹窗） */}
    </>
  );
}
