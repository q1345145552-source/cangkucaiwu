"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Key, UserPlus, MessageCircle, Pencil, DollarSign, Clock, History } from "lucide-react";

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
  const [newUser, setNewUser] = useState({ username: "", display_name: "", password: "", role: "staff" });

  // Edit user state
  const [editUser, setEditUser] = useState<any>(null);
  const [editPerms, setEditPerms] = useState<string[]>([]);

  useEffect(() => { if (!getToken()) router.push("/login"); if (tab === "users") loadUsers(); if (tab === "rates") loadRates(); }, [tab]);

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
    try { const r = await api.get<any>("/users?page_size=100"); setUsers(r.data); } catch {}
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
      await api.post("/users", newUser);
      toast("success", "创建成功");
      setNewUser({ username: "", display_name: "", password: "", role: "staff" });
      loadUsers();
    } catch (err: any) { toast("error", err.message || "创建失败"); }
  }

  function openEdit(u: any) {
    setEditUser(u);
    setEditPerms(u.extra_permissions || []);
  }

  function togglePerm(perm: string) {
    setEditPerms((prev) =>
      prev.includes(perm) ? prev.filter((p) => p !== perm) : [...prev, perm]
    );
  }

  async function saveEdit() {
    if (!editUser) return;
    try {
      await api.put(`/users/${editUser.id}`, { extra_permissions: editPerms });
      toast("success", "更新成功");
      setEditUser(null);
      loadUsers();
    } catch (err: any) { toast("error", err.message || "更新失败"); }
  }

  return (
    <>
      <div className="mb-4">
        <h1 className="page-title">{t("settings")}</h1>
        <div className="flex gap-3 mt-2">
          <button onClick={()=>setTab("profile")} className={`px-4 py-1.5 rounded text-sm ${tab==="profile"?"bg-primary text-white":"border"}`}>个人设置</button>
          {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
            <button onClick={()=>setTab("users")} className={`px-4 py-1.5 rounded text-sm ${tab==="users"?"bg-primary text-white":"border"}`}>用户管理</button>
          )}
          {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
            <button onClick={()=>setTab("rates")} className={`px-4 py-1.5 rounded text-sm ${tab==="rates"?"bg-primary text-white":"border"}`}>汇率管理</button>
          )}
        </div>
      </div>

      {tab === "profile" && (
        <div className="max-w-md space-y-6">
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
              <div><label className="form-label">{t("old_password")}</label><input type="password" className="form-input text-sm" value={pw.old} onChange={e=>setPw({...pw,old:e.target.value})} /></div>
              <div><label className="form-label">{t("new_password")}</label><input type="password" className="form-input text-sm" value={pw.new} onChange={e=>setPw({...pw,new:e.target.value})} /></div>
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
              <div><label className="form-label">用户名</label><input className="form-input text-sm" value={newUser.username} onChange={e=>setNewUser({...newUser,username:e.target.value})} /></div>
              <div><label className="form-label">显示名称</label><input className="form-input text-sm" value={newUser.display_name} onChange={e=>setNewUser({...newUser,display_name:e.target.value})} /></div>
              <div><label className="form-label">密码</label><input type="password" className="form-input text-sm" value={newUser.password} onChange={e=>setNewUser({...newUser,password:e.target.value})} /></div>
              <div><label className="form-label">角色</label><select className="form-input text-sm" value={newUser.role} onChange={e=>setNewUser({...newUser,role:e.target.value})}>
                <option value="staff">Staff 仓库财务</option>
                {user?.role === "super_admin" && <option value="warehouse_admin">WarehouseAdmin 仓库老板</option>}
              </select></div>
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
                  <td>{t(`role_${u.role}`)}</td><td>{u.warehouse_name || "-"}</td>
                  <td className="text-xs text-gray-500">
                    {u.extra_permissions && u.extra_permissions.length > 0
                      ? u.extra_permissions.map((p: string) => PERM_LABELS[p] || p).join(", ")
                      : "-"}
                  </td>
                  <td><span className={u.is_active ? "text-green-600" : "text-red-600"}>{u.is_active ? "启用" : "禁用"}</span></td>
                  <td>
                    {u.role === "staff" && (user?.role === "super_admin" || user?.role === "warehouse_admin") && (
                      <button onClick={() => openEdit(u)} className="text-primary text-xs hover:underline flex items-center gap-1">
                        <Pencil size={12} /> 权限
                      </button>
                    )}
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>

          {/* Edit permissions modal */}
          {editUser && (
            <div className="modal-overlay" onClick={() => setEditUser(null)}>
              <div className="bg-white rounded-xl w-full max-w-sm p-6" onClick={(e) => e.stopPropagation()}>
                <h2 className="text-lg font-semibold mb-1">编辑扩展权限</h2>
                <p className="text-sm text-gray-500 mb-4">{editUser.display_name} ({editUser.username})</p>
                <div className="space-y-2 mb-6">
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
    </>
  );
}