"use client";
import { useEffect, useState, useRef } from "react";
import { api, getToken, getActiveWarehouseId } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { UserPlus, Edit2, UserX, Users, Settings, ChevronDown, ChevronUp, Ban, Camera, Clock, Calendar, DollarSign, Tag, X as XIcon, TrendingUp } from "lucide-react";

export default function EmployeesPage() {
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [maxLimit, setMaxLimit] = useState(50);
  const [currentCount, setCurrentCount] = useState(0);
  const [showLimitSetting, setShowLimitSetting] = useState(false);
  const [resigningId, setResigningId] = useState<number | null>(null);
  const [resignForm, setResignForm] = useState({
    reason: "voluntary", resignation_date: new Date().toISOString().slice(0,10),
    blacklisted: false, blacklist_reason: "", note: ""
  });
  const [limitInput, setLimitInput] = useState("50");

  // Detail modal
  const [detailEmp, setDetailEmp] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [newTag, setNewTag] = useState("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [zoomedPhoto, setZoomedPhoto] = useState<string | null>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);

  const defaultForm: any = {
    name: "", position: "仓库劳工", myanmar_id: "", address: "",
    phone: "", emergency_contact: "", hire_date: "",
    status: "trial", daily_wage: 400, base_salary: 12000, remark: "",
    passport_number: "", work_permit_number: "",
    passport_expiry: "", work_permit_expiry: "",
    promotion_date: "", tags: "",
  };
  const [form, setForm] = useState({ ...defaultForm });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); loadLimit(); }, []);

  async function load() {
    setLoading(true);
    try {
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

  async function loadSummary(empId: number) {
    try {
      const r = await api.get<any>(`/employees/${empId}/summary`);
      setSummary(r);
    } catch { setSummary(null); }
  }

  async function handleCreate() {
    if (!form.name.trim()) { toast("error", "请输入姓名"); return; }
    try {
      const payload: any = { ...form };
      // Build comma-separated tags if it's an array
      if (Array.isArray(payload.tags)) {
        payload.tags = payload.tags.join(",");
      }
      if (editingId) {
        await api.put(`/employees/${editingId}`, payload);
        toast("success", "员工信息已更新");
        // Close detail modal if we were editing from there
        if (detailEmp && detailEmp.id === editingId) {
          await reloadDetail(editingId);
        }
      } else {
        const r = await api.post("/employees", payload);
        // Upload photo if selected
        if (photoFile && r && (r as any).id !== undefined) {
          await uploadPhoto((r as any).id);
        }
        toast("success", "员工创建成功");
      }
      if (!detailEmp) {
        setShowForm(false);
        setForm({ ...defaultForm });
        setEditingId(null);
      }
      setPhotoFile(null);
      load();
      loadLimit();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  async function uploadPhoto(empId?: number) {
    const targetId = empId || editingId;
    if (!targetId || !photoFile) return;
    setUploadingPhoto(true);
    try {
      const token = getToken();
      const fd = new FormData();
      fd.append("file", photoFile);
      const res = await fetch(`/api/v1/employees/${targetId}/photo`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd,
      });
      if (res.ok) {
        const r = await res.json();
        toast("success", "照片上传成功");
        if (detailEmp) {
          setDetailEmp({ ...detailEmp, photo_path: r.photo_path });
        }
      } else {
        const err = await res.json().catch(() => ({}));
        toast("error", err.detail || "上传失败");
      }
    } catch { toast("error", "照片上传失败"); }
    setUploadingPhoto(false);
    setPhotoFile(null);
    load();
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
      passport_number: e.passport_number || "",
      work_permit_number: e.work_permit_number || "",
      passport_expiry: e.passport_expiry || "",
      work_permit_expiry: e.work_permit_expiry || "",
      promotion_date: e.promotion_date || "",
      tags: Array.isArray(e.tags) ? e.tags.join(",") : (e.tags || ""),
    });
    setShowForm(true);
  }

  function openDetail(emp: any) {
    setDetailEmp(emp);
    loadSummary(emp.id);
  }

  async function reloadDetail(empId: number) {
    try {
      const r = await api.get<any>(`/employees/${empId}/summary`);
      setSummary(r);
      const updatedList = await api.get<any>("/employees?page_size=200");
      const found = (updatedList.data || []).find((e: any) => e.id === empId);
      if (found) setDetailEmp(found);
    } catch {}
  }

  async function resignEmployee() {
    if (!resigningId) return;
    try {
      const r = await api.post(`/employees/${resigningId}/resign`, resignForm);
      toast("success", r.message || "已标记为离职");
      setResigningId(null);
      if (detailEmp && detailEmp.id === resigningId) setDetailEmp(null);
      load();
      loadLimit();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  function openResignModal(id: number) {
    setResigningId(id);
    setResignForm({
      reason: "voluntary", resignation_date: new Date().toISOString().slice(0,10),
      blacklisted: false, blacklist_reason: "", note: ""
    });
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

  async function addTag() {
    if (!newTag.trim() || !detailEmp) return;
    const currentTags = Array.isArray(detailEmp.tags) ? detailEmp.tags : (detailEmp.tags ? detailEmp.tags.split(",").filter(Boolean) : []);
    if (currentTags.includes(newTag.trim())) { toast("error", "标签已存在"); return; }
    const updatedTags = [...currentTags, newTag.trim()].join(",");
    try {
      await api.put(`/employees/${detailEmp.id}`, { tags: updatedTags });
      toast("success", "标签已添加");
      setDetailEmp({ ...detailEmp, tags: [...currentTags, newTag.trim()] });
      setNewTag("");
      load();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  async function removeTag(tag: string) {
    if (!detailEmp) return;
    const currentTags = Array.isArray(detailEmp.tags) ? detailEmp.tags : (detailEmp.tags || "").split(",").filter(Boolean);
    const updatedTags = currentTags.filter((t: string) => t !== tag).join(",");
    try {
      await api.put(`/employees/${detailEmp.id}`, { tags: updatedTags });
      setDetailEmp({ ...detailEmp, tags: currentTags.filter((t: string) => t !== tag) });
      load();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  const activeEmployees = data.filter((e: any) => e.status !== "resigned");
  const isAdmin = user?.role === "warehouse_admin" || user?.role === "super_admin";

  return (
    <div>
      <div className="flex justify-between mb-4 flex-wrap gap-2 items-center">
        <h1 className="page-title flex items-center gap-2"><Users size={24}/>员工档案</h1>
        {user?.role === "warehouse_admin" && (
          <div className="flex gap-2 items-center">
            <div className="flex items-center gap-1 text-sm text-gray-500 bg-gray-100 rounded-lg px-3 py-1.5">
              <span>{currentCount}/{maxLimit}人</span>
              <button onClick={() => { setShowLimitSetting(!showLimitSetting); loadLimit(); }}
                className="p-1 hover:bg-gray-200 rounded"><Settings size={14}/></button>
            </div>
            {showLimitSetting && (
              <div className="flex items-center gap-2 bg-white border rounded-lg px-2 py-1">
                <input type="number" className="w-16 text-sm border rounded px-1 py-0.5" value={limitInput}
                  onChange={e => setLimitInput(e.target.value)} />
                <button onClick={saveMaxLimit} className="text-xs bg-blue-500 text-white px-2 py-1 rounded">保存</button>
              </div>
            )}
            <button onClick={() => { setEditingId(null); setForm({ ...defaultForm }); setPhotoFile(null); setShowForm(true); }}
              className="bg-primary text-white px-4 py-2 rounded-lg text-sm flex items-center gap-1">
              <UserPlus size={16}/>新建员工
            </button>
          </div>
        )}
        {user?.role === "super_admin" && (
          <button onClick={() => { setEditingId(null); setForm({ ...defaultForm }); setPhotoFile(null); setShowForm(true); }}
            className="bg-primary text-white px-4 py-2 rounded-lg text-sm flex items-center gap-1">
            <UserPlus size={16}/>新建员工
          </button>
        )}
      </div>

      {/* Active Employees Table */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-gray-50">
              <th className="text-left px-4 py-3 font-medium text-gray-600">姓名</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">岗位</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">状态</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">联系电话</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">入职日期</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">标签</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            {activeEmployees.map((e: any) => {
              const tags = Array.isArray(e.tags) ? e.tags : (e.tags ? e.tags.split(",").filter(Boolean) : []);
              return (
                <tr key={e.id} className="border-b hover:bg-gray-50 cursor-pointer" onClick={() => openDetail(e)}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      {e.photo_path ? (
                        <img src={`/${e.photo_path}`} className="w-10 h-10 rounded-full object-cover border cursor-pointer hover:ring-2 hover:ring-blue-300" onClick={e => { e.stopPropagation(); setZoomedPhoto(`/${e.photo_path}`); }} />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center text-gray-400 text-sm font-bold">
                          {e.name?.[0] || "?"}
                        </div>
                      )}
                      <div>
                        <span className="font-medium text-gray-800">{e.name}</span>
                        {e.blacklisted && <Ban size={12} className="inline ml-1 text-red-500" />}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{e.position || "-"}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      e.status === "trial" ? "bg-amber-50 text-amber-700" :
                      e.status === "regular" ? "bg-green-50 text-green-700" : "bg-gray-50 text-gray-500"
                    }`}>
                      {e.status === "trial" ? "试用期" : e.status === "regular" ? "正式" : e.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{e.phone || "-"}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{e.hire_date || "-"}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {tags.slice(0, 3).map((t: string) => (
                        <span key={t} className="px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded text-xs whitespace-nowrap">{t}</span>
                      ))}
                      {tags.length > 3 && <span className="text-xs text-gray-400">+{tags.length - 3}</span>}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                    {isAdmin && (
                      <div className="flex gap-1 justify-end">
                        <button onClick={() => editEmployee(e)} className="p-1.5 hover:bg-gray-100 rounded min-w-[32px]" title="编辑">
                          <Edit2 size={14} className="text-gray-400" />
                        </button>
                        <button onClick={() => openResignModal(e.id)}
                          className="p-1.5 hover:bg-red-50 rounded min-w-[32px]" title="离职">
                          <UserX size={14} className="text-red-400" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
            {activeEmployees.length === 0 && (
              <tr><td colSpan={7} className="text-center py-12 text-gray-400">暂无在职员工</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Resigned employees */}
      {data.filter((e: any) => e.status === "resigned").length > 0 && (
        <details className="mt-3 text-sm text-gray-400">
          <summary className="cursor-pointer">已离职员工 ({data.filter((e: any) => e.status === "resigned").length}人)</summary>
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

      {/* Create/Edit Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => { setShowForm(false); setPhotoFile(null); }}>
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-primary text-white px-5 py-3 rounded-t-2xl flex items-center gap-2 sticky top-0 z-10">
              <UserPlus size={20} />
              <span className="font-semibold">{editingId ? "编辑员工" : "新建员工"}</span>
              <button onClick={() => { setShowForm(false); setPhotoFile(null); }} className="ml-auto text-2xl">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              {/* Photo upload */}
              <div>
                <label className="form-label text-sm mb-1 block">员工照片</label>
                <div className="flex items-center gap-3">
                  {photoFile ? (
                    <img src={URL.createObjectURL(photoFile)} className="w-16 h-16 rounded-full object-cover border" />
                  ) : editingId && data.find(e => e.id === editingId)?.photo_path ? (
                    <img src={`/${data.find(e => e.id === editingId)?.photo_path}`} className="w-16 h-16 rounded-full object-cover border" />
                  ) : (
                    <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center text-gray-300">
                      <Camera size={24} />
                    </div>
                  )}
                  <label className="bg-gray-100 hover:bg-gray-200 px-3 py-1.5 rounded-lg text-sm cursor-pointer">
                    <input type="file" accept="image/*" className="hidden"
                      onChange={e => { const f = e.target.files?.[0]; if (f) setPhotoFile(f); }} />
                    {photoFile ? "更换照片" : "上传照片"}
                  </label>
                </div>
              </div>

              {/* Basic Info */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="form-label text-xs mb-1 block">姓名 <span className="text-red-400">*</span></label>
                  <input className="form-input py-2 w-full" value={form.name} onChange={e => setForm({...form, name: e.target.value})} />
                </div>
                <div>
                  <label className="form-label text-xs mb-1 block">岗位</label>
                  <select className="form-input py-2 w-full" value={form.position} onChange={e => setForm({...form, position: e.target.value})}>
                    <option value="仓库劳工">仓库劳工</option>
                    <option value="仓库主管">仓库主管</option>
                    <option value="叉车司机">叉车司机</option>
                    <option value="财务">财务</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="form-label text-xs mb-1 block">联系电话</label>
                  <input className="form-input py-2 w-full" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} />
                </div>
                <div>
                  <label className="form-label text-xs mb-1 block">缅甸身份证号</label>
                  <input className="form-input py-2 w-full" value={form.myanmar_id} onChange={e => setForm({...form, myanmar_id: e.target.value})} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="form-label text-xs mb-1 block">入职日期</label>
                  <input type="date" className="form-input py-2 w-full" value={form.hire_date} onChange={e => setForm({...form, hire_date: e.target.value})} />
                </div>
                <div>
                  <label className="form-label text-xs mb-1 block">员工状态</label>
                  <select className="form-input py-2 w-full" value={form.status} onChange={e => setForm({...form, status: e.target.value})}>
                    <option value="trial">试用期</option>
                    <option value="regular">正式</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="form-label text-xs mb-1 block">地址</label>
                <input className="form-input py-2 w-full" value={form.address} onChange={e => setForm({...form, address: e.target.value})} />
              </div>
              <div>
                <label className="form-label text-xs mb-1 block">紧急联系人</label>
                <input className="form-input py-2 w-full" value={form.emergency_contact} onChange={e => setForm({...form, emergency_contact: e.target.value})} />
              </div>

              {/* Passport & Work Permit */}
              <div className="border-t pt-3">
                <h4 className="text-sm font-medium text-gray-700 mb-3">护照 & 工作证</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="form-label text-xs mb-1 block">护照号码</label>
                    <input className="form-input py-2 w-full" value={form.passport_number || ""} onChange={e => setForm({...form, passport_number: e.target.value})} />
                  </div>
                  <div>
                    <label className="form-label text-xs mb-1 block">工作证号码</label>
                    <input className="form-input py-2 w-full" value={form.work_permit_number || ""} onChange={e => setForm({...form, work_permit_number: e.target.value})} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div>
                    <label className="form-label text-xs mb-1 block">护照有效期</label>
                    <input type="date" className="form-input py-2 w-full" value={form.passport_expiry || ""} onChange={e => setForm({...form, passport_expiry: e.target.value})} />
                  </div>
                  <div>
                    <label className="form-label text-xs mb-1 block">工作证有效期</label>
                    <input type="date" className="form-input py-2 w-full" value={form.work_permit_expiry || ""} onChange={e => setForm({...form, work_permit_expiry: e.target.value})} />
                  </div>
                </div>
              </div>

              {/* Salary & Promotion */}
              <div className="border-t pt-3">
                <h4 className="text-sm font-medium text-gray-700 mb-3">薪资 & 转正</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="form-label text-xs mb-1 block">试用期日薪 (泰铢)</label>
                    <input type="number" className="form-input py-2 w-full" value={form.daily_wage} onChange={e => setForm({...form, daily_wage: +e.target.value})} />
                  </div>
                  <div>
                    <label className="form-label text-xs mb-1 block">正式底薪 (泰铢/月)</label>
                    <input type="number" className="form-input py-2 w-full" value={form.base_salary} onChange={e => setForm({...form, base_salary: +e.target.value})} />
                  </div>
                </div>
                <div className="mt-3">
                  <label className="form-label text-xs mb-1 block">转正日期</label>
                  <input type="date" className="form-input py-2 w-full" value={form.promotion_date || ""} onChange={e => setForm({...form, promotion_date: e.target.value})} />
                  <p className="text-xs text-gray-400 mt-1">设置后，转正日之前按试用期日薪计算，之后按正式底薪计算</p>
                </div>
              </div>

              {/* Tags */}
              <div>
                <label className="form-label text-xs mb-1 block">标签（逗号分隔，如: 会说中文, 能开叉车）</label>
                <input className="form-input py-2 w-full" placeholder="会说中文, 能开叉车, 体力好" value={form.tags || ""} onChange={e => setForm({...form, tags: e.target.value})} />
              </div>

              <div>
                <label className="form-label text-xs mb-1 block">备注</label>
                <textarea className="form-input py-2 w-full" rows={2} value={form.remark} onChange={e => setForm({...form, remark: e.target.value})} placeholder="其他信息" />
              </div>
            </div>
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => { setShowForm(false); setPhotoFile(null); }} className="btn-secondary px-4 py-2 text-sm">取消</button>
              <button onClick={handleCreate} className="bg-primary text-white px-6 py-2 rounded-lg text-sm">
                {editingId ? "保存修改" : "创建员工"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Employee Detail Modal */}
      {detailEmp && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setDetailEmp(null)}>
          <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-xl" onClick={e => e.stopPropagation()}>
            {/* Photo Header */}
            <div className="relative h-40 bg-gradient-to-r from-blue-500 to-blue-600 rounded-t-2xl">
              <button onClick={() => setDetailEmp(null)} className="absolute top-3 right-3 text-2xl text-white/80 hover:text-white">&times;</button>
              <div className="absolute -bottom-8 left-5 flex items-end gap-4">
                <div className="relative group">
                  {detailEmp.photo_path ? (
                    <img src={`/${detailEmp.photo_path}`} className="w-20 h-20 rounded-full border-4 border-white object-cover shadow cursor-pointer hover:scale-105 transition-transform" onClick={() => setZoomedPhoto(`/${detailEmp.photo_path}`)} />
                  ) : (
                    <div className="w-20 h-20 rounded-full border-4 border-white bg-gray-200 flex items-center justify-center text-gray-400 text-2xl font-bold shadow">
                      {detailEmp.name?.[0] || "?"}
                    </div>
                  )}
                  <label className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-full opacity-0 group-hover:opacity-100 cursor-pointer transition">
                    <Camera size={18} className="text-white" />
                    <input type="file" accept="image/*" className="hidden"
                      onChange={e => { const f = e.target.files?.[0]; if (f) { setPhotoFile(f); setEditingId(detailEmp.id); } }} />
                  </label>
                </div>
                <div className="pb-2">
                  <h2 className="text-xl font-bold text-white">{detailEmp.name}</h2>
                  <span className="text-white/80 text-sm">{detailEmp.position || "仓库劳工"}</span>
                </div>
              </div>
            </div>

            <div className="px-5 pt-12 pb-5 space-y-5">
              {/* Status badges */}
              <div className="flex flex-wrap gap-2">
                <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                  detailEmp.status === "trial" ? "bg-amber-50 text-amber-700" : "bg-green-50 text-green-700"
                }`}>
                  {detailEmp.status === "trial" ? "试用期" : "正式员工"}
                </span>
                {detailEmp.blacklisted && (
                  <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-red-50 text-red-700">黑名单</span>
                )}
                {detailEmp.promotion_date && (
                  <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
                    转正: {detailEmp.promotion_date}
                  </span>
                )}
              </div>

              {/* Monthly Summary */}
              {summary && (
                <div className="bg-blue-50 rounded-xl p-4">
                  <h4 className="text-sm font-semibold text-blue-800 mb-3 flex items-center gap-1">
                    <TrendingUp size={16}/> 本月出勤 & 工资摘要
                  </h4>
                  <div className="grid grid-cols-4 gap-3 text-center">
                    <div><div className="text-2xl font-bold text-blue-700">{summary.attendance_days}</div><div className="text-xs text-blue-500">出勤天数</div></div>
                    <div><div className="text-2xl font-bold text-amber-600">{summary.late_count}</div><div className="text-xs text-amber-500">迟到次数</div></div>
                    <div><div className="text-2xl font-bold text-green-600">{summary.overtime_hours}h</div><div className="text-xs text-green-500">加班小时</div></div>
                    <div>
                      <div className="text-2xl font-bold text-blue-700">
                        {summary.payroll ? `${(summary.payroll.net_pay || 0).toLocaleString()}` : '-'}
                      </div>
                      <div className="text-xs text-blue-500">本月工资</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Basic Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-gray-400">联系电话</label>
                  <p className="text-sm text-gray-700 mt-0.5">{detailEmp.phone || "-"}</p>
                </div>
                <div>
                  <label className="text-xs text-gray-400">缅甸身份证号</label>
                  <p className="text-sm text-gray-700 mt-0.5">{detailEmp.myanmar_id || "-"}</p>
                </div>
                <div>
                  <label className="text-xs text-gray-400">入职日期</label>
                  <p className="text-sm text-gray-700 mt-0.5">{detailEmp.hire_date || "-"}</p>
                </div>
                <div>
                  <label className="text-xs text-gray-400">试用日薪 / 正式底薪</label>
                  <p className="text-sm text-gray-700 mt-0.5">{detailEmp.daily_wage} / {detailEmp.base_salary} 泰铢</p>
                </div>
                <div className="col-span-2">
                  <label className="text-xs text-gray-400">地址</label>
                  <p className="text-sm text-gray-700 mt-0.5">{detailEmp.address || "-"}</p>
                </div>
                <div className="col-span-2">
                  <label className="text-xs text-gray-400">紧急联系人</label>
                  <p className="text-sm text-gray-700 mt-0.5">{detailEmp.emergency_contact || "-"}</p>
                </div>
              </div>

              {/* Passport & Work Permit */}
              <div className="border-t pt-4">
                <h4 className="text-sm font-medium text-gray-700 mb-3">护照 & 工作证</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-gray-400">护照号码</label>
                    <p className="text-sm text-gray-700 mt-0.5">{detailEmp.passport_number || "-"}</p>
                  </div>
                  <div>
                    <label className="text-xs text-gray-400">工作证号码</label>
                    <p className="text-sm text-gray-700 mt-0.5">{detailEmp.work_permit_number || "-"}</p>
                  </div>
                  <div>
                    <label className="text-xs text-gray-400">护照有效期</label>
                    <p className="text-sm text-gray-700 mt-0.5">{detailEmp.passport_expiry || "-"}</p>
                  </div>
                  <div>
                    <label className="text-xs text-gray-400">工作证有效期</label>
                    <p className="text-sm text-gray-700 mt-0.5">{detailEmp.work_permit_expiry || "-"}</p>
                  </div>
                </div>
              </div>

              {/* Tags */}
              <div className="border-t pt-4">
                <h4 className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-1"><Tag size={14}/> 标签</h4>
                <div className="flex flex-wrap gap-2 mb-2">
                  {(Array.isArray(detailEmp.tags) ? detailEmp.tags : (detailEmp.tags || "").split(",").filter(Boolean)).map((t: string) => (
                    <span key={t} className="px-2 py-1 bg-blue-50 text-blue-600 rounded-full text-xs flex items-center gap-1">
                      {t}
                      <button onClick={() => removeTag(t)} className="text-blue-400 hover:text-red-500"><XIcon size={12}/></button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input className="form-input py-1.5 text-sm flex-1" placeholder="添加标签..." value={newTag}
                    onChange={e => setNewTag(e.target.value)} onKeyDown={e => e.key === "Enter" && addTag()} />
                  <button onClick={addTag} className="bg-blue-500 text-white px-3 py-1 rounded text-sm">添加</button>
                </div>
              </div>

              {/* Remark */}
              {detailEmp.remark && (
                <div className="border-t pt-4">
                  <label className="text-xs text-gray-400">备注</label>
                  <p className="text-sm text-gray-700 mt-0.5">{detailEmp.remark}</p>
                </div>
              )}

              {/* Created/Resigned info */}
              <div className="border-t pt-3 text-xs text-gray-400">
                {detailEmp.created_at && <span>创建于 {new Date(detailEmp.created_at).toLocaleString("zh-CN")}</span>}
                {detailEmp.resignation_date && <span className="ml-4 text-red-400">离职: {detailEmp.resignation_date} ({detailEmp.resignation_reason})</span>}
              </div>
            </div>

            {/* Action buttons */}
            <div className="border-t px-5 py-3 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              {detailEmp.status !== "resigned" && (
                <>
                  <button onClick={() => { editEmployee(detailEmp); setDetailEmp(null); }}
                    className="border border-gray-300 text-gray-600 px-4 py-2 rounded-lg text-sm flex items-center gap-1">
                    <Edit2 size={14}/> 编辑
                  </button>
                  <button onClick={() => { openResignModal(detailEmp.id); }}
                    className="bg-red-500 text-white px-4 py-2 rounded-lg text-sm flex items-center gap-1">
                    <UserX size={14}/> 离职
                  </button>
                </>
              )}
              <button onClick={() => setDetailEmp(null)} className="text-sm text-gray-400 px-4 py-2">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* Upload photo (triggered after file selection in detail modal) */}
      {photoFile && detailEmp && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-[60] p-4">
          <div className="bg-white rounded-xl p-6 text-center max-w-xs">
            <Camera size={32} className="mx-auto mb-3 text-blue-500" />
            <p className="text-sm text-gray-600 mb-4">上传 {detailEmp.name} 的照片？</p>
            <div className="flex gap-2 justify-center">
              <button onClick={() => setPhotoFile(null)} className="btn-secondary px-4 py-2 text-sm">取消</button>
              <button onClick={() => uploadPhoto(detailEmp.id)} disabled={uploadingPhoto}
                className="bg-blue-500 text-white px-4 py-2 rounded-lg text-sm">
                {uploadingPhoto ? "上传中..." : "确认上传"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Photo Zoom Overlay */}
      {zoomedPhoto && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-[70] p-4" onClick={() => setZoomedPhoto(null)}>
          <button onClick={() => setZoomedPhoto(null)}
            className="absolute top-4 right-4 text-white/70 hover:text-white text-4xl z-10 w-12 h-12 flex items-center justify-center">&times;</button>
          <img src={zoomedPhoto} alt="员工照片" className="max-w-full max-h-[90vh] rounded-lg shadow-2xl object-contain"
            onClick={e => e.stopPropagation()} />
        </div>
      )}

      {/* Resign Modal */}
      {resigningId && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={() => setResigningId(null)}>
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="bg-red-500 text-white px-5 py-3 rounded-t-2xl flex items-center gap-2">
              <UserX size={20} />
              <span className="font-semibold">标记离职</span>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">离职原因</label>
                <select className="form-input text-base py-2.5 w-full" value={resignForm.reason}
                  onChange={e => setResignForm({ ...resignForm, reason: e.target.value })}>
                  <option value="voluntary">正常离职</option>
                  <option value="absconded">自离</option>
                  <option value="fired">被辞退</option>
                  <option value="contract_end">合同到期</option>
                  <option value="other">其他</option>
                </select>
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">离职日期</label>
                <input type="date" className="form-input text-base py-2.5 w-full" value={resignForm.resignation_date}
                  onChange={e => setResignForm({ ...resignForm, resignation_date: e.target.value })} />
              </div>
              <div>
                <label className="form-label text-sm font-medium text-gray-600 mb-1 block">备注</label>
                <textarea className="form-input text-base py-2.5 w-full" rows={2} value={resignForm.note}
                  onChange={e => setResignForm({ ...resignForm, note: e.target.value })} placeholder="选填" />
              </div>
              {resignForm.reason === "fired" && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={resignForm.blacklisted}
                      onChange={e => setResignForm({ ...resignForm, blacklisted: e.target.checked })}
                      className="w-4 h-4 text-red-500 rounded" />
                    <span className="text-sm font-medium text-red-700">加入黑名单</span>
                  </label>
                  {resignForm.blacklisted && (
                    <textarea className="form-input mt-2 w-full text-sm py-2" rows={2} value={resignForm.blacklist_reason}
                      onChange={e => setResignForm({ ...resignForm, blacklist_reason: e.target.value })}
                      placeholder="黑名单原因" />
                  )}
                </div>
              )}
            </div>
            <div className="border-t px-5 py-4 bg-gray-50 rounded-b-2xl flex justify-end gap-3">
              <button onClick={() => setResigningId(null)} className="btn-secondary text-sm px-6 py-2">取消</button>
              <button onClick={resignEmployee} className="bg-red-500 text-white text-sm px-6 py-2 rounded-lg hover:bg-red-600">
                确认离职
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
