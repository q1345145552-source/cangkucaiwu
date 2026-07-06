"use client";
import { useEffect, useState } from "react";
import DataTable from "@/components/common/DataTable";
import { api, getToken } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useRouter } from "next/navigation";
import { Edit, Trash2, Power, PowerOff } from "lucide-react";

export default function AccountsPage() {
  const { toast } = useToast(); const router = useRouter();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({
    account_name: "", account_type: "bank", account_number: "", opening_balance: "",
    bank_name: "", branch_name: "", account_holder: "", currency: "THB", remark: ""
  });

  useEffect(() => { if (!getToken()) router.push("/login"); load(); }, []);

  async function load() {
    setLoading(true);
    try { const r = await api.get<any>("/accounts"); setData(r.data); } catch {}
    setLoading(false);
  }

  function openCreate() {
    setEditingId(null);
    setForm({ account_name: "", account_type: "bank", account_number: "", opening_balance: "", bank_name: "", branch_name: "", account_holder: "", currency: "THB", remark: "" });
    setShowForm(true);
  }

  function openEdit(row: any) {
    setEditingId(row.id);
    setForm({
      account_name: row.account_name || "",
      account_type: row.account_type || "bank",
      account_number: row.account_number || "",
      opening_balance: row.opening_balance != null ? String(row.opening_balance) : "",
      bank_name: row.bank_name || "",
      branch_name: row.branch_name || "",
      account_holder: row.account_holder || "",
      currency: row.currency || "THB",
      remark: row.remark || "",
    });
    setShowForm(true);
  }

  async function handleSave() {
    const payload = { ...form, opening_balance: form.opening_balance === "" ? 0 : +form.opening_balance };
    try {
      if (editingId) {
        await api.put(`/accounts/${editingId}`, payload);
        toast("success", "更新成功");
      } else {
        await api.post("/accounts", payload);
        toast("success", "创建成功");
      }
      setShowForm(false); load();
    } catch (err: any) { toast("error", err.message || "保存失败"); }
  }

  async function handleDelete(row: any) {
    if (!confirm(`确认删除账户"${row.account_name}"？`)) return;
    try { await api.delete(`/accounts/${row.id}`); toast("success", "删除成功"); load(); }
    catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  async function handleToggleStatus(row: any) {
    try {
      await api.put(`/accounts/${row.id}/toggle-status`, {});
      load();
    } catch (err: any) { toast("error", err.message || "操作失败"); }
  }

  const typeLabels: Record<string, string> = { bank: "银行", alipay: "支付宝", wechat: "微信" };
  const currencyLabels: Record<string, string> = { THB: "泰铢", CNY: "人民币" };

  const columns = [
    { key: "account_name", label: "账户名称" },
    { key: "account_holder", label: "账户持有人", render: (v: string) => v || "-" },
    { key: "account_type", label: "类型", render: (v: string) => typeLabels[v] || v },
    { key: "bank_name", label: "开户银行", render: (v: string) => v || "-" },
    { key: "account_number", label: "账号" },
    { key: "currency", label: "币种", render: (v: string) => currencyLabels[v] || v },
    { key: "opening_balance", label: "月初余额", align: "right" as const, render: (v: number) => v ? v.toLocaleString() : "0" },
    { key: "status", label: "状态", render: (v: string) => (
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${v === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
        {v === "active" ? "启用" : "停用"}
      </span>
    )},
    { key: "id", label: "操作", render: (_: any, row: any) => (
      <div className="flex items-center gap-1">
        <button onClick={() => handleToggleStatus(row)} className={`btn-xs flex items-center gap-0.5 ${row.status === "active" ? "text-orange-600 hover:bg-orange-50" : "text-green-600 hover:bg-green-50"} px-2 py-1 rounded`} title={row.status === "active" ? "停用" : "启用"}>
          {row.status === "active" ? <PowerOff size={12} /> : <Power size={12} />}
        </button>
        <button onClick={() => openEdit(row)} className="btn-secondary btn-xs flex items-center gap-0.5"><Edit size={12} />编辑</button>
        <button onClick={() => handleDelete(row)} className="btn-xs flex items-center gap-0.5 text-red-600 hover:bg-red-50 px-2 py-1 rounded"><Trash2 size={12} />删除</button>
      </div>
    )},
  ];

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h1 className="page-title">收款账户</h1>
        <button onClick={openCreate} className="btn-primary">新建账户</button>
      </div>

      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : (
        <DataTable columns={columns} data={data} total={data.length} page={1} pageSize={100} onPageChange={() => {}} />
      )}

      {/* 新建/编辑弹窗 */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Edit size={22} />
              <h2 className="text-lg font-semibold">{editingId ? "编辑收款账户" : "新建收款账户"}</h2>
              <div className="flex-1" />
              <button onClick={() => setShowForm(false)} className="text-blue-200 hover:text-white text-xl leading-none">&times;</button>
            </div>

            <div className="p-6 space-y-5">
              {/* 账户信息 */}
              <div>
                <div className="text-sm font-semibold text-gray-400 pb-2 border-b mb-3">账户信息</div>
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">账户名称 <span className="text-red-400">*</span></label>
                    <input className="form-input" value={form.account_name} onChange={e => setForm({ ...form, account_name: e.target.value })} placeholder="如：曼谷银行主账户" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">类型 <span className="text-red-400">*</span></label>
                    <select className="form-input" value={form.account_type} onChange={e => setForm({ ...form, account_type: e.target.value })}>
                      <option value="bank">银行</option>
                      <option value="alipay">支付宝</option>
                      <option value="wechat">微信</option>
                    </select>
                  </div>
                </div>
                <div className="form-group mt-3">
                  <label className="form-label">账户持有人</label>
                  <input className="form-input" value={form.account_holder} onChange={e => setForm({ ...form, account_holder: e.target.value })} placeholder="开户人姓名" />
                </div>
              </div>

              {/* 银行信息 - 仅银行类型显示 */}
              {form.account_type === "bank" && (
                <div>
                  <div className="text-sm font-semibold text-gray-400 pb-2 border-b mb-3">银行信息</div>
                  <div className="form-grid">
                    <div className="form-group">
                      <label className="form-label">开户银行</label>
                      <input className="form-input" value={form.bank_name} onChange={e => setForm({ ...form, bank_name: e.target.value })} placeholder="如：盘谷银行" />
                    </div>
                    <div className="form-group">
                      <label className="form-label">开户支行</label>
                      <input className="form-input" value={form.branch_name} onChange={e => setForm({ ...form, branch_name: e.target.value })} placeholder="如：曼谷分行" />
                    </div>
                  </div>
                  <div className="form-group mt-3">
                    <label className="form-label">账号 <span className="text-red-400">*</span></label>
                    <input className="form-input" value={form.account_number} onChange={e => setForm({ ...form, account_number: e.target.value })} placeholder="银行账号" />
                  </div>
                </div>
              )}

              {/* 非银行类型的账号 */}
              {form.account_type !== "bank" && (
                <div>
                  <div className="text-sm font-semibold text-gray-400 pb-2 border-b mb-3">账户信息</div>
                  <div className="form-group">
                    <label className="form-label">账号 <span className="text-red-400">*</span></label>
                    <input className="form-input" value={form.account_number} onChange={e => setForm({ ...form, account_number: e.target.value })} placeholder={form.account_type === "alipay" ? "支付宝账号" : "微信账号"} />
                  </div>
                </div>
              )}

              {/* 财务信息 */}
              <div>
                <div className="text-sm font-semibold text-gray-400 pb-2 border-b mb-3">财务信息</div>
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">币种</label>
                    <select className="form-input" value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })}>
                      <option value="THB">泰铢 (THB)</option>
                      <option value="CNY">人民币 (CNY)</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">月初余额</label>
                    <input type="number" className="form-input" value={form.opening_balance} onChange={e => setForm({ ...form, opening_balance: e.target.value })} placeholder="月初账户余额" />
                  </div>
                </div>
              </div>

              {/* 备注 */}
              <div>
                <div className="text-sm font-semibold text-gray-400 pb-2 border-b mb-3">备注</div>
                <div className="form-group">
                  <textarea className="form-input" rows={3} value={form.remark} onChange={e => setForm({ ...form, remark: e.target.value })} placeholder="其他备注信息" />
                </div>
              </div>
            </div>

            <div className="border-t px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="btn-secondary min-w-[80px]">取消</button>
              <button onClick={handleSave} className="btn-primary min-w-[80px]">{editingId ? "保存修改" : "新建账户"}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
