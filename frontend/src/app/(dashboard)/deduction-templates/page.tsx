"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { Scale, Plus, Edit2, Trash2 } from "lucide-react";

function fmtMultiplier(v: any): string {
  const n = Number(v ?? 0);
  return `${n}倍`;
}

export default function DeductionTemplatesPage() {
  const { toast } = useToast(); const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({
    name: "", late_half_multiplier: "0.5", late_one_multiplier: "1",
    late_half_threshold: "09:05", late_one_threshold: "09:31",
    early_half_multiplier: "0.5", early_one_multiplier: "1",
    early_half_threshold: "17:30", early_one_threshold: "17:00",
    absence_extra_multiplier: "0.5",
  });

  useEffect(() => { if (!getToken()) { router.push("/login"); return; } load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<any>("/deduction-templates");
      setRows(r.data || []);
    } catch (err: any) { toast("error", err.message || "加载扣款模板失败"); }
    setLoading(false);
  }

  function openCreate() {
    setEditingId(null);
    setForm({ name: "", late_half_multiplier: "0.5", late_one_multiplier: "1", late_half_threshold: "09:05", late_one_threshold: "09:31", early_half_multiplier: "0.5", early_one_multiplier: "1", early_half_threshold: "17:30", early_one_threshold: "17:00", absence_extra_multiplier: "0.5" });
    setShowForm(true);
  }

  function openEdit(r: any) {
    setEditingId(r.id);
    setForm({
      name: r.name,
      late_half_multiplier: String(r.late_half_multiplier ?? 0.5),
      late_one_multiplier: String(r.late_one_multiplier ?? 1),
      late_half_threshold: r.late_half_threshold || "09:05",
      late_one_threshold: r.late_one_threshold || "09:31",
      early_half_multiplier: String(r.early_half_multiplier ?? 0.5),
      early_one_multiplier: String(r.early_one_multiplier ?? 1),
      early_half_threshold: r.early_half_threshold || "17:30",
      early_one_threshold: r.early_one_threshold || "17:00",
      absence_extra_multiplier: String(r.absence_extra_multiplier ?? 0.5),
    });
    setShowForm(true);
  }

  async function handleSave() {
    if (!form.name.trim()) { toast("error", "请填写模板名称"); return; }
    if (!form.late_half_threshold || !form.late_one_threshold) { toast("error", "请填写迟到红线"); return; }
    if (form.late_half_threshold >= form.late_one_threshold) {
      toast("error", "迟到半小时红线要早于迟到1小时红线"); return;
    }
    if (!form.early_half_threshold || !form.early_one_threshold) { toast("error", "请填写早退红线"); return; }
    if (form.early_one_threshold >= form.early_half_threshold) {
      toast("error", "早退1小时红线要早于早退半小时红线"); return;
    }
    const payload = {
      name: form.name.trim(),
      late_half_multiplier: parseFloat(form.late_half_multiplier) || 0,
      late_one_multiplier: parseFloat(form.late_one_multiplier) || 0,
      late_half_threshold: form.late_half_threshold,
      late_one_threshold: form.late_one_threshold,
      early_half_multiplier: parseFloat(form.early_half_multiplier) || 0,
      early_one_multiplier: parseFloat(form.early_one_multiplier) || 0,
      early_half_threshold: form.early_half_threshold,
      early_one_threshold: form.early_one_threshold,
      absence_extra_multiplier: parseFloat(form.absence_extra_multiplier) || 0,
    };
    try {
      if (editingId) {
        await api.put(`/deduction-templates/${editingId}`, payload);
        toast("success", "扣款模板已更新");
      } else {
        await api.post("/deduction-templates", payload);
        toast("success", "扣款模板创建成功");
      }
      setShowForm(false);
      load();
    } catch (err: any) { toast("error", err.message || "保存失败"); }
  }

  async function handleDelete(r: any) {
    if (r.usage_count > 0) { toast("error", `有 ${r.usage_count} 个员工在使用该模板，不能删除`); return; }
    if (!confirm(`确定删除模板「${r.name}」吗？`)) return;
    try {
      await api.delete(`/deduction-templates/${r.id}`);
      toast("success", "扣款模板已删除");
      load();
    } catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  const numField = (label: string, key: string) => (
    <div>
      <label className="form-label text-sm font-medium text-gray-600 mb-1 block">{label}</label>
      <input type="number" step="0.1" min="0" className="form-input py-2.5 w-full"
        value={(form as any)[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} />
    </div>
  );

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><Scale size={24}/>扣款模板</h1>
        <button onClick={openCreate} className="btn-primary flex items-center gap-1 text-sm px-4 py-2">
          <Plus size={16}/> 新建模板
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border">
          <Scale size={40} className="mx-auto mb-3 text-gray-300"/>
          <p>暂无扣款模板</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border overflow-x-auto">
          <table className="w-full text-sm min-w-[760px]">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left px-3 py-3 font-medium text-gray-500">模板名称</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">迟到扣款</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">早退扣款</th>
                <th className="text-left px-3 py-3 font-medium text-gray-500">旷工额外罚</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">使用人数</th>
                <th className="text-center px-3 py-3 font-medium text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-3 py-3 font-medium">{r.name}</td>
                  <td className="px-3 py-3">
                    <div>半小时{fmtMultiplier(r.late_half_multiplier)} · 1小时{fmtMultiplier(r.late_one_multiplier)}</div>
                    <div className="text-xs text-gray-400">红线 {r.late_half_threshold || "09:05"} / {r.late_one_threshold || "09:31"}</div>
                  </td>
                  <td className="px-3 py-3">
                    <div>半小时{fmtMultiplier(r.early_half_multiplier)} · 1小时{fmtMultiplier(r.early_one_multiplier)}</div>
                    <div className="text-xs text-gray-400">红线 {r.early_one_threshold || "17:00"} / {r.early_half_threshold || "17:30"}</div>
                  </td>
                  <td className="px-3 py-3">{fmtMultiplier(r.absence_extra_multiplier)}</td>
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
          <div className="bg-white rounded-2xl w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <Scale size={20} /><span className="font-semibold">{editingId ? "编辑模板" : "新建模板"}</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">模板名称</label>
                <input className="form-input py-2.5 w-full" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="如：标准扣款" />
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-2 block">迟到扣款（时薪的倍数）</label>
                <div className="grid grid-cols-2 gap-3">
                  {numField("迟到半小时", "late_half_multiplier")}
                  {numField("迟到1小时", "late_one_multiplier")}
                </div>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-2 block">迟到红线 <span className="text-red-400">*</span></label>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="form-label text-xs text-gray-500 mb-1 block">迟到半小时红线</label>
                    <input type="time" className="form-input py-2.5 w-full" value={form.late_half_threshold}
                      onChange={e => setForm({ ...form, late_half_threshold: e.target.value })} />
                  </div>
                  <div>
                    <label className="form-label text-xs text-gray-500 mb-1 block">迟到1小时红线</label>
                    <input type="time" className="form-input py-2.5 w-full" value={form.late_one_threshold}
                      onChange={e => setForm({ ...form, late_one_threshold: e.target.value })} />
                  </div>
                </div>
                <p className="text-xs text-gray-400 mt-1">迟到半小时红线必须早于迟到1小时红线</p>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-2 block">早退扣款（时薪的倍数）</label>
                <div className="grid grid-cols-2 gap-3">
                  {numField("早退半小时", "early_half_multiplier")}
                  {numField("早退1小时", "early_one_multiplier")}
                </div>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-2 block">早退红线 <span className="text-red-400">*</span></label>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="form-label text-xs text-gray-500 mb-1 block">早退半小时红线</label>
                    <input type="time" className="form-input py-2.5 w-full" value={form.early_half_threshold}
                      onChange={e => setForm({ ...form, early_half_threshold: e.target.value })} />
                  </div>
                  <div>
                    <label className="form-label text-xs text-gray-500 mb-1 block">早退1小时红线</label>
                    <input type="time" className="form-input py-2.5 w-full" value={form.early_one_threshold}
                      onChange={e => setForm({ ...form, early_one_threshold: e.target.value })} />
                  </div>
                </div>
                <p className="text-xs text-gray-400 mt-1">早退1小时红线必须早于早退半小时红线</p>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">旷工额外罚（日薪的倍数）</label>
                <input type="number" step="0.1" min="0" className="form-input py-2.5 w-full" value={form.absence_extra_multiplier}
                  onChange={e => setForm({ ...form, absence_extra_multiplier: e.target.value })} />
                <p className="text-xs text-gray-400 mt-1">旷工当天除不计算工资外，额外再罚日薪的该倍数</p>
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
