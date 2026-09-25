"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Key, UserPlus, MessageCircle, Pencil, Trash2, DollarSign, Clock, History, Phone } from "lucide-react";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

const PERM_LABELS: Record<string, string> = {
  "到账流水": "到账流水",
  "备用金管理": "备用金管理",
  "报销管理": "报销管理",
  "收付款管理": "收付款管理",
  "账期管理": "账期管理",
  "操作日志": "操作日志",
  "供应商管理": "供应商管理",
  "其他收支": "其他收支",
};

export default function SettingsPage() {
  const { t } = useI18n();
  const { toast } = useToast(); const { user } = useAuth(); const router = useRouter();
  const [tab, setTab] = useState<"profile"|"users"|"rates">("profile");
  const [pw, setPw] = useState({ old: "", new: "" });
  const [pwMsg, setPwMsg] = useState("");
  const [lineId, setLineId] = useState("");
  const [rates, setRates] = useState<any[]>([]);
  const [rateForm, setRateForm] = useState({ from_currency: "CNY", to_currency: "THB", rate: "" });
  const [rateLoading, setRateLoading] = useState(false);
  const [users, setUsers] = useState<any[]>([]);
  const [newUser, setNewUser] = useState({ username: "", display_name: "", password: "", role: "warehouse_admin", warehouse_id: "", warehouse_ids: [] as number[] });
  const [warehouses, setWarehouses] = useState<any[]>([]);
  // 老板联系方式
  const [bossContact, setBossContact] = useState({ name: "", phone: "" });
  // 仓库排班设置
  const [schedule, setSchedule] = useState({ morning_start: "09:00", noon_break_start: "12:00", noon_break_end: "13:00", afternoon_end: "18:00" });
  const [scheduleEditable, setScheduleEditable] = useState(false);
  const [scheduleSaving, setScheduleSaving] = useState(false);

  // Edit user state
  const [editUser, setEditUser] = useState<any>(null);
  const [editPerms, setEditPerms] = useState<string[]>([]);
  const [editUsername, setEditUsername] = useState("");
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editPassword, setEditPassword] = useState("");
  const [editWarehouseId, setEditWarehouseId] = useState<number | string>("");
  const [editWarehouseIds, setEditWarehouseIds] = useState<number[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<any>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => { if (!getToken()) router.push("/login"); if (tab === "users") { loadUsers(); loadWarehouses(); } if (tab === "rates") loadRates(); }, [tab]);
  useEffect(() => { if (user?.role === "warehouse_admin" || user?.role === "super_admin") loadBossContact(); }, [user?.role]);
  useEffect(() => { if (user?.role === "warehouse_admin" || user?.role === "supervisor") loadSchedule(); }, [user?.role]);

  async function loadSchedule() {
    try {
      const r = await api.get<any>("/settings/schedule");
      setSchedule({
        morning_start: r.morning_start || "09:00",
        noon_break_start: r.noon_break_start || "12:00",
        noon_break_end: r.noon_break_end || "13:00",
        afternoon_end: r.afternoon_end || "18:00",
      });
      setScheduleEditable(!!r.editable);
    } catch {}
  }
  async function saveSchedule() {
    setScheduleSaving(true);
    try {
      await api.put("/settings/schedule", schedule);
      toast("success", "排班设置已保存");
      loadSchedule();
    } catch (err: any) { toast("error", err.message || "保存失败"); }
    setScheduleSaving(false);
  }

  async function loadBossContact() {
    try { const r = await api.get<any>("/settings/boss-contact"); setBossContact({ name: r.name || "", phone: r.phone || "" }); } catch {}
  }
  async function saveBossContact() {
    try {
      await api.put("/settings/boss-contact", bossContact);
      toast("success", "老板联系方式已保存");
    } catch (err: any) { toast("error", err.message || "保存失败"); }
  }
  useEffect(() => {
    if (user?.role === "warehouse_admin" || user?.role === "supervisor") {
      setNewUser(prev => ({ ...prev, role: "staff" }));
    } else if (user?.role === "super_admin") {
      setNewUser(prev => ({ ...prev, role: "warehouse_admin" }));
    }
  }, [user?.role]);

  async function loadWarehouses() {
    try { const r = await api.get<any>("/warehouses?page=1&page_size=100"); setWarehouses(r.data || []); } catch {}
  }

  async function loadRates() {
    setRateLoading(true);
    try { const r = await api.get<any>("/rates"); setRates(r.data || []); } catch {}
    setRateLoading(false);
  }

  async function setRate() {
    try {
      await api.post("/rates", { ...rateForm, rate: rateForm.rate ? +rateForm.rate : 0 });
      toast("success", "汇率设定成功");
      setRateForm({ from_currency: "CNY", to_currency: "THB", rate: "" });
      loadRates();
    } catch (err: any) { toast("error", err.message || "设定失败"); }
  }

  async function loadUsers() {
    try {
      const url = user?.role === "super_admin" ? "/users?page_size=100&role=warehouse_admin" : "/users?page_size=100";
      const r = await api.get<any>(url); setUsers(r.data);
    } catch {}
  }

  async function changePassword() {
    try { await api.post("/auth/change-password", { old_password: pw.old, new_password: pw.new }); setPwMsg("密码修改成功"); setPw({ old: "", new: "" }); }
    catch(e: any) { setPwMsg(e.message); }
  }

  async function bindLine() {
    await api.put(`/users/${user?.id}`, { line_user_id: lineId });
    alert("LINE 账号绑定成功");
  }

  async function createUser() {
    try {
      if (newUser.role === "supervisor") {
        if (newUser.warehouse_ids.length === 0) {
          toast("error", "请选择所属仓库");
          return;
        }
      } else if (newUser.role !== "warehouse_admin" && !newUser.warehouse_id) {
        toast("error", "请选择所属仓库");
        return;
      }
      const payload: any = {
        username: newUser.username,
        display_name: newUser.display_name,
        password: newUser.password,
        role: newUser.role,
      };
      if (newUser.role === "supervisor") {
        payload.warehouse_ids = newUser.warehouse_ids;
      } else if (newUser.role !== "warehouse_admin") {
        payload.warehouse_id = +newUser.warehouse_id;
      }
      await api.post("/users", payload);
      toast("success", "创建成功");
      setNewUser({ username: "", display_name: "", password: "", role: user?.role === "super_admin" ? "warehouse_admin" : "staff", warehouse_id: "", warehouse_ids: [] });
      loadUsers();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  function openEdit(u: any) {
    setEditUser(u);
    setEditPerms(u.extra_permissions || []);
    setEditUsername(u.username || "");
    setEditDisplayName(u.display_name || "");
    setEditPassword("");
    setEditWarehouseId(u.warehouse_id || "");
    setEditWarehouseIds(u.warehouse_ids || []);
  }

  function toggleWarehouseId(wid: number) {
    setEditWarehouseIds((prev) =>
      prev.includes(wid) ? prev.filter((x) => x !== wid) : [...prev, wid]
    );
  }

  function togglePerm(perm: string) {
    setEditPerms((prev) =>
      prev.includes(perm) ? prev.filter((p) => p !== perm) : [...prev, perm]
    );
  }

  async function saveEdit() {
    if (!editUser) return;
    try {
      const payload: any = {
        username: editUsername,
        display_name: editDisplayName,
        extra_permissions: editPerms,
      };
      if (editPassword) payload.password = editPassword;
      if (editUser.role === "supervisor") {
        payload.warehouse_ids = editWarehouseIds;
      } else if (editWarehouseId) {
        payload.warehouse_id = +editWarehouseId;
      }
      await api.put(`/users/${editUser.id}`, payload);
      toast("success", "更新成功");
      setEditUser(null);
      loadUsers();
    } catch (err: any) { toast("error", err.message || "更新失败"); }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/users/${deleteTarget.id}`);
      toast("success", "删除成功");
      setDeleteTarget(null);
      loadUsers();
    } catch (err: any) { toast("error", err.message || "删除失败"); }
    setDeleting(false);
  }

  return (
    <>
      <div className="mb-4">
        <h1 className="page-title">{t("settings")}</h1>
        <div className="flex gap-3 mt-2">
          <button onClick={()=>setTab("profile")} className={`px-4 py-1.5 rounded text-sm ${tab==="profile"?"bg-primary text-white":"border"}`}>个人设置</button>
          {(user?.role === "super_admin" || user?.role === "warehouse_admin" || user?.role === "supervisor") && (
            <button onClick={()=>setTab("users")} className={`px-4 py-1.5 rounded text-sm ${tab==="users"?"bg-primary text-white":"border"}`}>用户管理</button>
          )}
          {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
            <button onClick={()=>setTab("rates")} className={`px-4 py-1.5 rounded text-sm ${tab==="rates"?"bg-primary text-white":"border"}`}>汇率管理</button>
          )}
        </div>
      </div>

      {tab === "profile" && (
        <div className="max-w-md space-y-6">
          {/* 老板联系方式 */}
          {(user?.role === "warehouse_admin" || user?.role === "super_admin") && (
            <div className="bg-white rounded-xl p-4 shadow-sm">
              <h3 className="font-semibold mb-3 flex items-center gap-2"><Phone size={18} className="text-blue-500"/> 老板联系方式</h3>
              <div className="text-xs text-gray-400 mb-3">显示在采购单 PDF 上的联系人信息</div>
              <div className="space-y-3">
                <div><label className="form-label">老板称呼</label><input className="form-input text-sm" placeholder="如：王老板" value={bossContact.name} onChange={e=>setBossContact({...bossContact, name: e.target.value})} /></div>
                <div><label className="form-label">电话号码</label><input className="form-input text-sm" placeholder="如：+66 812345678" value={bossContact.phone} onChange={e=>setBossContact({...bossContact, phone: e.target.value})} /></div>
                <button onClick={saveBossContact} className="btn-primary">保存联系方式</button>
              </div>
            </div>
          )}

          {/* 仓库排班设置 */}
          {(user?.role === "warehouse_admin" || user?.role === "supervisor") && (
            <div className="bg-white rounded-xl p-4 shadow-sm">
              <h3 className="font-semibold mb-3 flex items-center gap-2"><Clock size={18} className="text-indigo-500"/> 仓库排班设置</h3>
              <div className="text-xs text-gray-400 mb-3">每个仓库单独设置上下班时间，修改后打卡、补卡、加班默认时间同步生效</div>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="form-label text-xs">早上上班时间</label>
                    <input type="time" className="form-input text-sm" value={schedule.morning_start}
                      disabled={!scheduleEditable}
                      onChange={e => setSchedule({ ...schedule, morning_start: e.target.value })} />
                  </div>
                  <div>
                    <label className="form-label text-xs">中午休息开始</label>
                    <input type="time" className="form-input text-sm" value={schedule.noon_break_start}
                      disabled={!scheduleEditable}
                      onChange={e => setSchedule({ ...schedule, noon_break_start: e.target.value })} />
                  </div>
                  <div>
                    <label className="form-label text-xs">中午休息结束</label>
                    <input type="time" className="form-input text-sm" value={schedule.noon_break_end}
                      disabled={!scheduleEditable}
                      onChange={e => setSchedule({ ...schedule, noon_break_end: e.target.value })} />
                  </div>
                  <div>
                    <label className="form-label text-xs">下午下班时间</label>
                    <input type="time" className="form-input text-sm" value={schedule.afternoon_end}
                      disabled={!scheduleEditable}
                      onChange={e => setSchedule({ ...schedule, afternoon_end: e.target.value })} />
                  </div>
                </div>
                {!scheduleEditable && <div className="text-xs text-gray-400">仅仓库管理员可修改</div>}
                {scheduleEditable && (
                  <button onClick={saveSchedule} disabled={scheduleSaving} className="btn-primary">
                    {scheduleSaving ? "保存中..." : "保存排班"}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* LINE Binding */}
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <h3 className="font-semibold mb-3 flex items-center gap-2"><MessageCircle size={18} className="text-green-500"/> 绑定 LINE 账号</h3>
            <div className="flex gap-2">
              <input className="border rounded px-3 py-2 flex-1 text-sm" placeholder="LINE User ID" value={lineId} onChange={e=>setLineId(e.target.value)} />
              <button onClick={bindLine} className="bg-green-500 text-white px-4 py-2 rounded text-sm">绑定</button>
            </div>
            <div className="text-xs text-gray-400 mt-2">绑定后可接收备用金警报、审批通知、逾期提醒等消息</div>
          </div>

          {/* Change Password */}
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <h3 className="font-semibold mb-3 flex items-center gap-2"><Key size={18}/> {t("change_password")}</h3>
            <div className="space-y-3">
              <div><label className="form-label">{t("old_password")}</label><input type="password" className="form-input text-sm" value={pw.old} onChange={e=>setPw({...pw,old:e.target.value})} autoComplete="off" /></div>
              <div><label className="form-label">{t("new_password")}</label><input type="password" className="form-input text-sm" value={pw.new} onChange={e=>setPw({...pw,new:e.target.value})} autoComplete="new-password" /></div>
              <button onClick={changePassword} className="btn-primary">修改密码</button>
              {pwMsg && <div className="text-sm text-green-600">{pwMsg}</div>}
            </div>
          </div>
        </div>
      )}

      {tab === "users" && (
        <div>
          <div className="bg-white rounded-xl p-4 shadow-sm mb-4 max-w-md">
            <h3 className="font-semibold mb-3 flex items-center gap-2"><UserPlus size={18}/> {t("create_user")}</h3>
            <div className="space-y-3">
              <div><label className="form-label">用户名</label><input className="form-input text-sm" value={newUser.username} onChange={e=>setNewUser({...newUser,username:e.target.value})} autoComplete="off" /></div>
              <div><label className="form-label">显示名称</label><input className="form-input text-sm" value={newUser.display_name} onChange={e=>setNewUser({...newUser,display_name:e.target.value})} autoComplete="off" /></div>
              <div><label className="form-label">密码</label><input type="password" className="form-input text-sm" value={newUser.password} onChange={e=>setNewUser({...newUser,password:e.target.value})} autoComplete="new-password" /></div>
              <div><label className="form-label">角色</label><select className="form-input text-sm" value={newUser.role} onChange={e=>setNewUser({...newUser,role:e.target.value})}>
                {user?.role === "super_admin" && <option value="warehouse_admin">仓库管理员</option>}
                {user?.role === "warehouse_admin" && (<>
                  <option value="supervisor">仓库主管</option>
                  <option value="staff">仓库财务</option>
                  <option value="warehouse_labor">仓库劳工</option>
                </>)}
                {user?.role === "supervisor" && (<>
                  <option value="staff">仓库财务</option>
                  <option value="warehouse_labor">仓库劳工</option>
                </>)}
              </select></div>
              {newUser.role !== "warehouse_admin" && (
                <div><label className="form-label">所属仓库 <span className="text-red-400">*</span></label>
                {newUser.role === "supervisor" ? (
                  <div className="border rounded p-2 space-y-1 max-h-48 overflow-y-auto">
                    {warehouses.map((w:any) => (
                      <label key={w.id} className="flex items-center gap-2 cursor-pointer py-1">
                        <input type="checkbox" checked={newUser.warehouse_ids.includes(w.id)}
                          onChange={(e) => setNewUser(prev => ({
                            ...prev,
                            warehouse_ids: e.target.checked
                              ? [...prev.warehouse_ids, w.id]
                              : prev.warehouse_ids.filter(x => x !== w.id),
                          }))} />
                        <span className="text-sm">{w.name}（{w.code}）</span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <select className="form-input text-sm" value={newUser.warehouse_id} onChange={e=>setNewUser({...newUser,warehouse_id:e.target.value})}>
                    <option value="">请选择仓库</option>
                    {warehouses.map((w:any) => <option key={w.id} value={w.id}>{w.name}（{w.code}）</option>)}
                  </select>
                )}
                </div>
              )}
              <button onClick={createUser} className="btn-primary">创建用户</button>
            </div>
          </div>

          {/* User list */}
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b"><tr><th className="text-left px-4 py-2">用户名</th><th>显示名</th><th>角色</th><th>仓库</th><th>扩展权限</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>{users.map((u:any)=>(
                <tr key={u.id} className="border-b">
                  <td className="px-4 py-2">{u.username}</td><td>{u.display_name}</td>
                  <td>{t(`role_${u.role}`)}</td>
                  <td>{u.warehouse_ids && u.warehouse_ids.length > 1 ? `${u.warehouse_ids.length} 个仓库` : (u.warehouse_name || "-")}</td>
                  <td className="text-xs text-gray-500">
                    {u.extra_permissions && u.extra_permissions.length > 0
                      ? u.extra_permissions.map((p: string) => PERM_LABELS[p] || p).join(", ")
                      : "-"}
                  </td>
                  <td><span className={u.is_active ? "text-green-600" : "text-red-600"}>{u.is_active ? "启用" : "禁用"}</span></td>
                  <td>
                    <div className="flex items-center gap-2">
                      {(user?.role === "warehouse_admin" || user?.role === "supervisor") && (u.role === "staff" || u.role === "warehouse_labor") && (
                        <>
                          <button onClick={() => openEdit(u)} className="text-primary text-xs hover:underline flex items-center gap-1">
                            <Pencil size={12} /> 编辑
                          </button>
                          <button onClick={() => setDeleteTarget(u)} className="text-red-500 text-xs hover:underline flex items-center gap-1">
                            <Trash2 size={12} /> 删除
                          </button>
                        </>
                      )}
                      {user?.role === "super_admin" && u.role === "warehouse_admin" && (
                        <button onClick={() => setDeleteTarget(u)} className="text-red-500 text-xs hover:underline flex items-center gap-1">
                          <Trash2 size={12} /> 删除
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>

          {/* Edit user modal */}
          {editUser && (
            <div className="modal-overlay" onClick={() => setEditUser(null)}>
              <div className="bg-white rounded-xl w-full max-w-sm p-6 max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
                <h2 className="text-lg font-semibold mb-1">编辑用户</h2>
                <p className="text-sm text-gray-500 mb-4">{editUser.display_name} ({editUser.username})</p>
                <div className="space-y-3 mb-4">
                  <div><label className="form-label text-xs">用户名</label><input className="form-input text-sm" value={editUsername} onChange={e => setEditUsername(e.target.value)} /></div>
                  <div><label className="form-label text-xs">显示名</label><input className="form-input text-sm" value={editDisplayName} onChange={e => setEditDisplayName(e.target.value)} /></div>
                  <div><label className="form-label text-xs">重置密码（留空表示不改）</label><input type="password" className="form-input text-sm" value={editPassword} onChange={e => setEditPassword(e.target.value)} autoComplete="new-password" placeholder="留空不修改密码" /></div>
                  {(user?.role === "warehouse_admin" || user?.role === "supervisor") && (
                    <div><label className="form-label text-xs">所属仓库</label>
                      {editUser.role === "supervisor" ? (
                        <div className="border rounded p-2 space-y-1 max-h-48 overflow-y-auto">
                          {warehouses.map((w: any) => (
                            <label key={w.id} className="flex items-center gap-2 cursor-pointer py-1">
                              <input type="checkbox" checked={editWarehouseIds.includes(w.id)}
                                onChange={() => toggleWarehouseId(w.id)} />
                              <span className="text-sm">{w.name}（{w.code}）</span>
                            </label>
                          ))}
                        </div>
                      ) : (
                        <select className="form-input text-sm" value={editWarehouseId} onChange={e => setEditWarehouseId(e.target.value)}>
                          <option value="">请选择仓库</option>
                          {warehouses.map((w: any) => <option key={w.id} value={w.id}>{w.name}（{w.code}）</option>)}
                        </select>
                      )}
                    </div>
                  )}
                </div>
                <div className="mb-4">
                  <div className="text-sm font-medium mb-2">扩展权限</div>
                  <div className="space-y-1">
                    {Object.entries(PERM_LABELS).map(([key, label]) => (
                      <label key={key} className="flex items-center gap-2 cursor-pointer py-1">
                        <input
                          type="checkbox"
                          checked={editPerms.includes(key)}
                          onChange={() => togglePerm(key)}
                          className="rounded"
                        />
                        <span className="text-sm">{label}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="flex justify-end gap-3">
                  <button onClick={() => setEditUser(null)} className="btn-secondary">取消</button>
                  <button onClick={saveEdit} className="px-4 py-2 bg-primary text-white rounded-lg text-sm">保存</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "rates" && (
        <div>
          {/* Set new rate */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-4 max-w-md">
            <h3 className="font-semibold mb-4 flex items-center gap-2"><DollarSign size={18} className="text-blue-600" /> 设定新汇率</h3>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="form-label text-xs">从币种</label>
                  <select className="form-input text-sm" value={rateForm.from_currency} onChange={e => setRateForm({...rateForm, from_currency: e.target.value})}>
                    <option value="CNY">CNY 人民币</option>
                    <option value="THB">THB 泰铢</option>
                    <option value="USD">USD 美元</option>
                  </select>
                </div>
                <div>
                  <label className="form-label text-xs">到币种</label>
                  <select className="form-input text-sm" value={rateForm.to_currency} onChange={e => setRateForm({...rateForm, to_currency: e.target.value})}>
                    <option value="THB">THB 泰铢</option>
                    <option value="CNY">CNY 人民币</option>
                    <option value="USD">USD 美元</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="form-label text-xs">汇率</label>
                <input type="number" step="0.001" className="form-input text-sm" placeholder="例如 5.0" value={rateForm.rate} onChange={e => setRateForm({...rateForm, rate: e.target.value})} />
              </div>
              <div className="text-xs text-gray-400 flex items-center gap-1">
                <Clock size={12} /> 保存时自动记录当前时间为生效时间，每次修改新增一条记录
              </div>
              <button onClick={setRate} className="btn-primary w-full">设定汇率</button>
            </div>
          </div>

          {/* Rate history */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
            <h3 className="font-semibold mb-4 flex items-center gap-2"><History size={18} className="text-indigo-600" /> 汇率变更记录</h3>
            {rateLoading ? (
              <div className="flex items-center justify-center h-24 text-gray-400">
                <div className="animate-spin w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full mr-2" />
                加载中...
              </div>
            ) : rates.length === 0 ? (
              <div className="text-center py-8 text-gray-400 text-sm">暂无汇率记录</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="text-left px-4 py-3 font-medium text-gray-500">生效时间</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-500">从币种</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-500">到币种</th>
                      <th className="text-right px-4 py-3 font-medium text-gray-500">汇率</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-500">设定人</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rates.map((r: any) => (
                      <tr key={r.id} className="border-b hover:bg-gray-50/50">
                        <td className="px-4 py-3 text-gray-600">{r.effective_from ? new Date(r.effective_from).toLocaleString("zh-CN") : "-"}</td>
                        <td className="px-4 py-3"><span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700">{r.from_currency}</span></td>
                        <td className="px-4 py-3"><span className="px-2 py-0.5 rounded text-xs font-medium bg-green-50 text-green-700">{r.to_currency}</span></td>
                        <td className="px-4 py-3 text-right font-mono font-medium">{r.rate?.toFixed(3)}</td>
                        <td className="px-4 py-3 text-gray-500">{r.set_by_name || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="删除用户"
        message={user?.role === "warehouse_admin"
          ? `确定要删除 ${deleteTarget?.display_name} (${deleteTarget?.username}) 吗？删除后该账号将无法登录，此操作不可恢复。`
          : `确定要删除 ${deleteTarget?.display_name} (${deleteTarget?.username}) 吗？该用户创建的所有仓库和数据将被彻底删除，此操作不可恢复。`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </>
  );
}