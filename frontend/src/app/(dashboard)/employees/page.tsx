"use client";
import { useEffect, useState } from "react";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { UserPlus, Edit2, UserX, Users, Settings, ChevronDown, ChevronUp } from "lucide-react";

export default function EmployeesPage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [maxLimit, setMaxLimit] = useState(50);
  const [currentCount, setCurrentCount] = useState(0);
  const [showLimitSetting, setShowLimitSetting] = useState(false);
  const [limitInput, setLimitInput] = useState("50");
  
  const defaultForm = {
    name: "", position: "仓库劳工", myanmar_id: "", address: "",
    phone: "", emergency_contact: "", hire_date: "",
    status: "trial", daily_wage: 400, base_salary: 12000, remark: "",
  };
  const [form, setForm] = useState({ ...defaultForm });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadLimit(); }, []);

  async function load() {
    setLoading(true);
    try {
      const whId = getActiveWarehouseId();
      const headers: Record<string, string> = {};
      if (whId) headers["X-Warehouse-ID"] = whId;
      const r = await api.get<any>("/employees?page_size=200");
      setData(r.data || []);
    } catch {}
    setLoading(false);
  }

  async function loadLimit() {
    try {
      const r = await api.get<any>("/employees/max-limit");
      setMaxLimit(r.max_employees || 50);
      setCurrentCount(r.current_count || 0);
      setLimitInput(String(r.max_employees || 50));
    } catch {}
  }

  async function handleCreate() {
    if (!form.name.trim()) { toast("error", "请输入姓名"); return; }
    try {
      if (editingId) {
        await api.put(`/employees/${editingId}`, form);
        toast("success", "员工信息已更新");
      } else {
        await api.post("/employees", form);
        toast("success", "员工创建成功");
      }
      setShowForm(false);
      setForm({ ...defaultForm });
      setEditingId(null);
      load();
      loadLimit();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  function editEmployee(e: any) {
    setEditingId(e.id);
    setForm({
      name: e.name || "", position: e.position || "仓库劳工",
      myanmar_id: e.myanmar_id || "", address: e.address || "",
      phone: e.phone || "", emergency_contact: e.emergency_contact || "",
      hire_date: e.hire_date || "", status: e.status || "trial",
      daily_wage: e.daily_wage ?? 400, base_salary: e.base_salary ?? 12000,
      remark: e.remark || "",
    });
    setShowForm(true);
  }

  async function resignEmployee(id: number) {
    if (!confirm("确定将该员工标记为离职吗？")) return;
    try {
      await api.post(`/employees/${id}/resign`);
      toast("success", "已标记为离职");
      load();
      loadLimit();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  async function saveMaxLimit() {
    try {
      const v = parseInt(limitInput) || 50;
      await api.put(`/employees/max-limit?max_employees=${v}`, {});
      setMaxLimit(v);
      toast("success", `人数上限已设为 ${v}`);
      setShowLimitSetting(false);
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  const activeEmployees = data.filter((e: any) => e.status !== "resigned");
  const isAdmin = user?.role === "warehouse_admin";

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><Users size={24}/>员工档案</h1>
        {isAdmin && (
          <div className="flex gap-2 items-center">
            <div className="flex items-center gap-1 text-sm text-gray-500 bg-gray-100 rounded-lg px-3 py-1.5">
              <span>{currentCount}/{maxLimit}人</span>
              <button onClick={() => { setShowLimitSetting(!showLimitSetting); loadLimit(); }}
                className="p-1 hover:bg-gray-200 rounded"><Settings size={14}/></button>
            </div>
            {showLimitSetting && (
              <div className="flex items-center gap-2 bg-white border rounded-lg px-3 py-1.5 shadow-sm">
                <span className="text-xs text-gray-400">上限</span>
                <input type="number" value={limitInput} onChange={e => setLimitInput(e.target.value)}
                  className="w-16 border rounded px-2 py-0.5 text-sm text-center" />
                <button onClick={saveMaxLimit} className="text-xs bg-blue-500 text-white px-2 py-0.5 rounded">确定</button>
              </div>
            )}
            <button onClick={() => { setEditingId(null); setForm({ ...defaultForm }); setShowForm(true); }}
              className={`btn-primary flex items-center gap-1 ${currentCount >= maxLimit ? "opacity-50 cursor-not-allowed" : ""}`}
              disabled={currentCount >= maxLimit}>
              <UserPlus size={16}/>新建员工
            </button>
          </div>
        )}
      </div>

      {currentCount >= maxLimit && isAdmin && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
          员工人数已达上限 {maxLimit} 人，无法新增。如需增加请调整上限。
        </div>
      )}

      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : (
        <div className="bg-white rounded-xl border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left px-4 py-3 font-medium text-gray-500">姓名</th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">岗位</th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">联系电话</th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">入职日期</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500">状态</th>
                <th className="text-center px-4 py-3 font-medium text-gray-500 w-[160px]">操作</th>
              </tr>
            </thead>
            <tbody>
              {activeEmployees.map((e: any) => (
                <tr key={e.id} className="border-b hover:bg-gray-50/50">
                  <td className="px-4 py-3 font-medium">{e.name}</td>
                  <td className="px-4 py-3 text-gray-500">{e.position || "-"}</td>
                  <td className="px-4 py-3 text-gray-500">{e.phone || "-"}</td>
                  <td className="px-4 py-3 text-gray-500">{e.hire_date || "-"}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      e.status === "regular" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"
                    }`}>
                      {e.status === "regular" ? "正式" : "试用期"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {isAdmin && (
                        <>
                          <button onClick={() => editEmployee(e)}
                            className="text-blue-500 hover:bg-blue-50 p-1.5 rounded text-xs"><Edit2 size={14}/></button>
                          {e.status === "trial" && (
                            <button onClick={async () => {
                              try { await api.put(`/employees/${e.id}`, { status: "regular" }); toast("success", "已转为正式"); load(); }
                              catch (err: any) { toast("error", err.message); }
                            }} className="text-green-500 hover:bg-green-50 p-1.5 rounded text-xs" title="转正">转正</button>
                          )}
                          <button onClick={() => resignEmployee(e.id)}
                            className="text-red-400 hover:bg-red-50 p-1.5 rounded text-xs"><UserX size={14}/></button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {activeEmployees.length === 0 && (
                <tr><td colSpan={6} className="text-center py-12 text-gray-400">暂无员工</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Form Modal */}
      {showForm && (
        <div className="modal-overlay z-50" onClick={() => { setShowForm(false); setEditingId(null); }}>
          <div className="bg-white rounded-2xl w-[600px] max-h-[85vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-5 py-3.5 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <UserPlus size={18} />
              <h2 className="font-semibold">{editingId ? "编辑员工" : "新建员工"}</h2>
              <button onClick={() => { setShowForm(false); setEditingId(null); }}
                className="ml-auto text-blue-200 hover:text-white text-xl leading-none">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">姓名 <span className="text-red-400">*</span></label>
                  <input className="form-input text-base py-2.5" placeholder="员工姓名" value={form.name}
                    onChange={e => setForm({ ...form, name: e.target.value })} />
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">岗位</label>
                  <input className="form-input text-base py-2.5" placeholder="如 仓库劳工" value={form.position}
                    onChange={e => setForm({ ...form, position: e.target.value })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">缅甸身份证号</label>
                  <input className="form-input text-base py-2.5" placeholder="身份证号" value={form.myanmar_id}
                    onChange={e => setForm({ ...form, myanmar_id: e.target.value })} />
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">联系电话</label>
                  <input className="form-input text-base py-2.5" placeholder="电话号码" value={form.phone}
                    onChange={e => setForm({ ...form, phone: e.target.value })} />
                </div>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">住址</label>
                <input className="form-input text-base py-2.5" placeholder="住址" value={form.address}
                  onChange={e => setForm({ ...form, address: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">紧急联系人</label>
                  <input className="form-input text-base py-2.5" placeholder="紧急联系人及电话" value={form.emergency_contact}
                    onChange={e => setForm({ ...form, emergency_contact: e.target.value })} />
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">入职日期</label>
                  <input type="date" className="form-input text-base py-2.5" value={form.hire_date}
                    onChange={e => setForm({ ...form, hire_date: e.target.value })} />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">员工状态</label>
                  <select className="form-input text-base py-2.5" value={form.status}
                    onChange={e => setForm({ ...form, status: e.target.value })}>
                    <option value="trial">试用期</option>
                    <option value="regular">正式</option>
                  </select>
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">日薪 (泰铢)</label>
                  <input type="number" className="form-input text-base py-2.5" value={form.daily_wage || ""}
                    onChange={e => setForm({ ...form, daily_wage: e.target.value === "" ? 0 : +e.target.value })} />
                </div>
                <div>
                  <label className="form-label text-sm font-medium text-gray-600 mb-1 block">底薪 (泰铢)</label>
                  <input type="number" className="form-input text-base py-2.5" value={form.base_salary || ""}
                    onChange={e => setForm({ ...form, base_salary: e.target.value === "" ? 0 : +e.target.value })} />
                </div>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">备注</label>
                <textarea className="form-input text-base py-2.5" rows={2} placeholder="备注信息" value={form.remark}
                  onChange={e => setForm({ ...form, remark: e.target.value })} />
              </div>
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => { setShowForm(false); setEditingId(null); }}
                className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={handleCreate} className="btn-primary text-sm px-6 py-2">
                {editingId ? "保存修改" : "创建员工"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Resigned Employees */}
      {data.some((e: any) => e.status === "resigned") && (
        <details className="mt-6">
          <summary className="text-sm text-gray-400 cursor-pointer hover:text-gray-600 flex items-center gap-1">
            <ChevronDown size={14} className="hidden details-open:block" />
            <ChevronUp size={14} className="block details-open:hidden" />
            已离职员工 ({data.filter((e: any) => e.status === "resigned").length}人)
          </summary>
          <div className="mt-2 bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm opacity-60">
              <thead>
                <tr className="border-b bg-gray-50">
                  <th className="text-left px-4 py-2 font-medium text-gray-400">姓名</th>
                  <th className="text-left px-4 py-2 font-medium text-gray-400">岗位</th>
                  <th className="text-left px-4 py-2 font-medium text-gray-400">联系电话</th>
                  <th className="text-left px-4 py-2 font-medium text-gray-400">入职日期</th>
                </tr>
              </thead>
              <tbody>
                {data.filter((e: any) => e.status === "resigned").map((e: any) => (
                  <tr key={e.id} className="border-b border-gray-50">
                    <td className="px-4 py-2 line-through">{e.name}</td>
                    <td className="px-4 py-2 text-gray-400">{e.position || "-"}</td>
                    <td className="px-4 py-2 text-gray-400">{e.phone || "-"}</td>
                    <td className="px-4 py-2 text-gray-400">{e.hire_date || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
