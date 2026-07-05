"use client";
import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/hooks/useI18n";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Key, UserPlus, MessageCircle, Pencil } from "lucide-react";

const PERM_LABELS: Record<string, string> = {
  incoming_entry: "录入到账流水",
  approve_expense_fund: "审批备用金",
  approve_reimbursement: "审批报销",
  confirm_income: "确认入账",
  confirm_expense: "确认出账",
  manage_credit: "管理账期",
  operation_log: "查看操作日志",
};

export default function SettingsPage() {
  const { t } = useI18n(); const { user } = useAuth(); const router = useRouter();
  const [tab, setTab] = useState<"profile"|"users">("profile");
  const [pw, setPw] = useState({ old: "", new: "" });
  const [pwMsg, setPwMsg] = useState("");
  const [lineId, setLineId] = useState("");
  const [users, setUsers] = useState<any[]>([]);
  const [newUser, setNewUser] = useState({ username: "", display_name: "", password: "", role: "staff" });

  // Edit user state
  const [editUser, setEditUser] = useState<any>(null);
  const [editPerms, setEditPerms] = useState<string[]>([]);

  useEffect(() => { if (!getToken()) router.push("/login"); if (tab === "users") loadUsers(); }, [tab]);

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
    await api.post("/users", newUser);
    setNewUser({ username: "", display_name: "", password: "", role: "staff" });
    loadUsers();
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
    await api.put(`/users/${editUser.id}`, { extra_permissions: editPerms });
    setEditUser(null);
    loadUsers();
  }

  return (
    <>
      <div className="mb-4">
        <h1 className="text-xl font-bold">{t("settings")}</h1>
        <div className="flex gap-3 mt-2">
          <button onClick={()=>setTab("profile")} className={`px-4 py-1.5 rounded text-sm ${tab==="profile"?"bg-primary text-white":"border"}`}>个人设置</button>
          {(user?.role === "super_admin" || user?.role === "warehouse_admin") && (
            <button onClick={()=>setTab("users")} className={`px-4 py-1.5 rounded text-sm ${tab==="users"?"bg-primary text-white":"border"}`}>用户管理</button>
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
              <div><label className="text-sm">{t("old_password")}</label><input type="password" className="border rounded px-3 py-2 w-full text-sm" value={pw.old} onChange={e=>setPw({...pw,old:e.target.value})} /></div>
              <div><label className="text-sm">{t("new_password")}</label><input type="password" className="border rounded px-3 py-2 w-full text-sm" value={pw.new} onChange={e=>setPw({...pw,new:e.target.value})} /></div>
              <button onClick={changePassword} className="bg-primary text-white px-4 py-2 rounded text-sm">修改密码</button>
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
              <div><label className="text-sm">用户名</label><input className="border rounded px-3 py-2 w-full text-sm" value={newUser.username} onChange={e=>setNewUser({...newUser,username:e.target.value})} /></div>
              <div><label className="text-sm">显示名称</label><input className="border rounded px-3 py-2 w-full text-sm" value={newUser.display_name} onChange={e=>setNewUser({...newUser,display_name:e.target.value})} /></div>
              <div><label className="text-sm">密码</label><input type="password" className="border rounded px-3 py-2 w-full text-sm" value={newUser.password} onChange={e=>setNewUser({...newUser,password:e.target.value})} /></div>
              <div><label className="text-sm">角色</label><select className="border rounded px-3 py-2 w-full text-sm" value={newUser.role} onChange={e=>setNewUser({...newUser,role:e.target.value})}>
                <option value="staff">Staff 仓库财务</option>
                {user?.role === "super_admin" && <option value="warehouse_admin">WarehouseAdmin 仓库老板</option>}
              </select></div>
              <button onClick={createUser} className="bg-primary text-white px-4 py-2 rounded text-sm">创建用户</button>
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
            <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={() => setEditUser(null)}>
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
                  <button onClick={() => setEditUser(null)} className="px-4 py-2 border rounded-lg text-sm">取消</button>
                  <button onClick={saveEdit} className="px-4 py-2 bg-primary text-white rounded-lg text-sm">保存</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
