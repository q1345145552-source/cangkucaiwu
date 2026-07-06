"use client";
import { useEffect, useState } from "react";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { api, getToken } from "@/lib/api";
import { useRouter } from "next/navigation";
import DataTable from "@/components/common/DataTable";
import { Edit, Trash2 } from "lucide-react";

export default function CustomersPage() {
  const { t } = useI18n();
  const { toast } = useToast();
  const router = useRouter();
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [creditFilter, setCreditFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    customer_code: "", company_name: "", contact_person: "", contact_info: "",
    line_id: "", cargo_type: "", logistics_channel: "",
    default_currency: "THB", default_payment_method: "", credit_status: false, credit_limit: "", debt_amount: "", remark: ""
  });

  useEffect(() => { if (!getToken()) router.push("/login"); }, []);

  async function load() {
    setLoading(true);
    try {
      let url = `/customers?page=${page}&page_size=20&search=${search}`;
      if (creditFilter) url += `&credit_status=${creditFilter}`;
      const res = await api.get<any>(url);
      setData(res.data); setTotal(res.total);
    } catch {}
    setLoading(false);
  }

  useEffect(() => { load(); }, [page, search, creditFilter]);

  function openCreate() {
    setEditingId(null);
    setForm({ customer_code: "", company_name: "", contact_person: "", contact_info: "", line_id: "", cargo_type: "", logistics_channel: "", default_currency: "THB", default_payment_method: "", credit_status: false, credit_limit: "", debt_amount: "", remark: "" });
    setShowForm(true);
  }

  function openEdit(row: any) {
    setEditingId(row.id);
    setForm({
      customer_code: row.customer_code || "",
      company_name: row.company_name || "",
      contact_person: row.contact_person || "",
      contact_info: row.contact_info || "",
      line_id: row.line_id || "",
      cargo_type: row.cargo_type || "",
      logistics_channel: row.logistics_channel || "",
      default_currency: row.default_currency || "THB",
      default_payment_method: row.default_payment_method || "",
      credit_status: row.credit_status || false,
      credit_limit: row.credit_limit != null ? String(row.credit_limit) : "",
      debt_amount: row.debt_amount != null ? String(row.debt_amount) : "",
      remark: row.remark || "",
    });
    setShowForm(true);
  }

  async function handleSave() {
    try {
      const payload = {
        ...form,
        credit_limit: form.credit_limit === "" ? 0 : +form.credit_limit,
        debt_amount: form.debt_amount === "" ? 0 : +form.debt_amount,
      };
      if (editingId) {
        await api.put(`/customers/${editingId}`, payload);
        toast("success", "更新成功");
      } else {
        await api.post("/customers", payload);
        toast("success", "创建成功");
      }
      setShowForm(false); load();
    } catch (err: any) { toast("error", err.message || "保存失败"); }
  }

  async function handleDelete(row: any) {
    if (!confirm(`确认删除客户"${row.company_name}"？\n删除后不可恢复。`)) return;
    try {
      await api.delete(`/customers/${row.id}`);
      toast("success", "删除成功");
      load();
    } catch (err: any) { toast("error", err.message || "删除失败"); }
  }

  const cargoTypeLabel = (v: string) => {
    const map: Record<string, string> = { general: "普货", sensitive: "敏感货", brand: "品牌货" };
    return map[v] || v || "-";
  };

  const columns = [
    { key: "customer_code", label: "客户编号" },
    { key: "company_name", label: "公司名称" },
    { key: "contact_person", label: "联系人" },
    { key: "line_id", label: "微信账号", render: (v: string) => v || "-" },
    { key: "cargo_type", label: "常用货品", render: (v: string) => cargoTypeLabel(v) },
    { key: "total_shipments", label: "累计发货", align: "right" as const },
    { key: "total_shipping_cost", label: "累计运费", align: "right" as const, render: (v: number) => v ? `¥${v.toLocaleString()}` : "-" },
    { key: "credit_status", label: "账期客户", render: (v: boolean) => v ? <span className="text-green-600 text-xs font-medium">是</span> : <span className="text-gray-400 text-xs">否</span> },
    { key: "debt_amount", label: "欠款", align: "right" as const, render: (v: number) => v ? <span className="text-red-500 font-medium">¥{v.toLocaleString()}</span> : "-" },
    { key: "id", label: "操作", render: (_: any, row: any) => (
      <div className="flex items-center gap-1">
        <button onClick={() => openEdit(row)} className="btn-secondary btn-xs flex items-center gap-0.5"><Edit size={12} />编辑</button>
        <button onClick={() => handleDelete(row)} className="btn-xs flex items-center gap-0.5 text-red-600 hover:bg-red-50 px-2 py-1 rounded"><Trash2 size={12} />删除</button>
      </div>
    )},
  ];

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h1 className="page-title">客户档案</h1>
        <button onClick={openCreate} className="btn-primary">新建客户</button>
      </div>

      {/* 筛选栏 */}
      <div className="card mb-4 p-4">
        <div className="flex items-end gap-3">
          <div className="w-64">
            <input type="text" placeholder="搜索客户名称或编号..." value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="form-input" />
          </div>
          <div className="w-36">
            <select className="form-input" value={creditFilter} onChange={e => { setCreditFilter(e.target.value); setPage(1); }}>
              <option value="">全部客户</option>
              <option value="true">账期客户</option>
              <option value="false">非账期客户</option>
            </select>
          </div>
        </div>
      </div>

      {loading ? <div className="text-center py-8 text-gray-400">加载中...</div> : <DataTable columns={columns} data={data} total={total} page={page} pageSize={20} onPageChange={setPage} />}

      {/* 新建/编辑弹窗 */}
      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-xl w-full max-w-xl max-h-[90vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-blue-600 text-white px-6 py-4 rounded-t-xl flex items-center gap-3">
              <Edit size={22} />
              <h2 className="text-lg font-semibold">{editingId ? "编辑客户" : "新建客户"}</h2>
              <div className="flex-1" />
              <button onClick={() => setShowForm(false)} className="text-blue-200 hover:text-white text-xl leading-none">&times;</button>
            </div>

            <div className="p-6 space-y-5">
              {/* 基本信息 */}
              <div>
                <div className="text-sm font-semibold text-gray-400 pb-2 border-b mb-3">基本信息</div>
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">客户编号 <span className="text-red-400">*</span></label>
                    <input className="form-input" value={form.customer_code} onChange={e => setForm({ ...form, customer_code: e.target.value })} placeholder="如：CUS001" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">公司名称 <span className="text-red-400">*</span></label>
                    <input className="form-input" value={form.company_name} onChange={e => setForm({ ...form, company_name: e.target.value })} placeholder="客户公司全称" />
                  </div>
                </div>
              </div>

              {/* 联系信息 */}
              <div>
                <div className="text-sm font-semibold text-gray-400 pb-2 border-b mb-3">联系信息</div>
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">联系人</label>
                    <input className="form-input" value={form.contact_person} onChange={e => setForm({ ...form, contact_person: e.target.value })} placeholder="对方联系人姓名" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">联系方式</label>
                    <input className="form-input" value={form.contact_info} onChange={e => setForm({ ...form, contact_info: e.target.value })} placeholder="电话号码" />
                  </div>
                </div>
                <div className="form-group mt-3">
                  <label className="form-label">微信账号</label>
                  <input className="form-input" value={form.line_id} onChange={e => setForm({ ...form, line_id: e.target.value })} placeholder="微信ID" />
                </div>
              </div>

              {/* 发货信息 */}
              <div>
                <div className="text-sm font-semibold text-gray-400 pb-2 border-b mb-3">发货信息</div>
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">常用货品类型</label>
                    <select className="form-input" value={form.cargo_type} onChange={e => setForm({ ...form, cargo_type: e.target.value })}>
                      <option value="">未设置</option>
                      <option value="general">普货</option>
                      <option value="sensitive">敏感货</option>
                      <option value="brand">品牌货</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">常用物流渠道</label>
                    <input className="form-input" value={form.logistics_channel} onChange={e => setForm({ ...form, logistics_channel: e.target.value })} placeholder="如：海运-深圳仓" />
                  </div>
                </div>
              </div>

              {/* 财务信息 */}
              <div>
                <div className="text-sm font-semibold text-gray-400 pb-2 border-b mb-3">财务信息</div>
                <div className="form-grid mb-3">
                  <div className="form-group">
                    <label className="form-label">默认币种</label>
                    <select className="form-input" value={form.default_currency} onChange={e => setForm({ ...form, default_currency: e.target.value })}>
                      <option value="THB">泰铢 (THB)</option>
                      <option value="CNY">人民币 (CNY)</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">默认付款方式</label>
                    <select className="form-input" value={form.default_payment_method} onChange={e => setForm({ ...form, default_payment_method: e.target.value })}>
                      <option value="">未设置</option>
                      <option value="alipay">支付宝</option>
                      <option value="wechat">微信</option>
                      <option value="bank_transfer">银行转账</option>
                    </select>
                  </div>
                </div>
                <label className="flex items-center gap-2 cursor-pointer mb-3">
                  <input type="checkbox" checked={form.credit_status} onChange={e => setForm({ ...form, credit_status: e.target.checked })} className="w-4 h-4" />
                  <span className="text-sm">账期客户</span>
                </label>
                {form.credit_status && (
                  <div className="form-grid">
                    <div className="form-group">
                      <label className="form-label">账期额度</label>
                      <input type="number" className="form-input" value={form.credit_limit} onChange={e => setForm({ ...form, credit_limit: e.target.value })} placeholder="授信额度金额" />
                    </div>
                    <div className="form-group">
                      <label className="form-label">当前欠款</label>
                      <input type="number" className="form-input" value={form.debt_amount} onChange={e => setForm({ ...form, debt_amount: e.target.value })} placeholder="当前欠款金额" />
                    </div>
                  </div>
                )}
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
              <button onClick={handleSave} className="btn-primary min-w-[80px]">{editingId ? "保存修改" : "新建客户"}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
