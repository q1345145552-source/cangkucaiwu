"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useI18n } from "@/hooks/useI18n";
import { useToast } from "@/components/ui/Toast";
import { api, getToken } from "@/lib/api";
import { Warehouse, Plus, Pencil, Trash2 } from "lucide-react";

interface WhItem {
  id: number;
  name: string;
  name_th: string;
  code: string;
  address: string | null;
  is_active: boolean;
}

export default function WarehousesPage() {
  const { t } = useI18n();
  const { toast } = useToast();
  const { user } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<WhItem[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ name: "", name_th: "", code: "", address: "", is_active: true });

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    if (user?.role !== "super_admin") { router.push("/dashboard"); return; }
    load();
  }, [user]);

  async function load() {
    try {
      const res = await api.get<{ data: WhItem[] }>("/warehouses");
      setData(res.data || []);
    } catch {}
  }

  async function handleSave() {
    if (editId) {
      await api.put(`/warehouses/${editId}`, form);
        toast("success", "更新成功");
    } else {
      await api.post("/warehouses", form);
        toast("success", "创建成功");
    }
    setShowForm(false);
    setEditId(null);
    setForm({ name: "", name_th: "", code: "", address: "", is_active: true });
    load();
  }

  function openEdit(w: WhItem) {
    setEditId(w.id);
    setForm({ name: w.name, name_th: w.name_th || "", code: w.code, address: w.address || "", is_active: w.is_active });
    setShowForm(true);
  }

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <h1 className="page-title">仓库管理</h1>
        <button
          onClick={() => { setEditId(null); setForm({ name: "", name_th: "", code: "", address: "", is_active: true }); setShowForm(true); }}
          className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded-lg text-sm"
        >
          <Plus size={16} /> 新建仓库
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.map((wh) => (
          <div key={wh.id} className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                  <Warehouse size={20} className="text-blue-600" />
                </div>
                <div>
                  <div className="font-semibold text-gray-800">{wh.name}</div>
                  <div className="text-xs text-gray-400">{wh.name_th}</div>
                </div>
              </div>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${wh.is_active ? "bg-green-50 text-green-600" : "bg-gray-100 text-gray-400"}`}>
                {wh.is_active ? "启用" : "停用"}
              </span>
            </div>
            <div className="text-xs text-gray-500 space-y-1 mb-3">
              <div>编码: {wh.code}</div>
              {wh.address && <div>地址: {wh.address}</div>}
            </div>
            <div className="flex gap-2 pt-3 border-t">
              <button onClick={() => openEdit(wh)} className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800">
                <Pencil size={12} /> 编辑
              </button>
            </div>
          </div>
        ))}
      </div>

      {data.length === 0 && (
        <div className="text-center py-16 text-gray-400">暂无仓库数据，点击上方按钮新建</div>
      )}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-xl w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-4">{editId ? "编辑仓库" : "新建仓库"}</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-sm mb-1">仓库名称（中文）</label>
                <input className="form-input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="如：曼谷1仓" />
              </div>
              <div>
                <label className="block text-sm mb-1">ชื่อคลังสินค้า (ไทย)</label>
                <input className="form-input" value={form.name_th} onChange={e => setForm({ ...form, name_th: e.target.value })} placeholder="如：คลังสินค้ากรุงเทพ 1" />
              </div>
              <div>
                <label className="block text-sm mb-1">仓库编码</label>
                <input className="form-input" value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} placeholder="如：BKK1" />
              </div>
              <div>
                <label className="block text-sm mb-1">地址（选填）</label>
                <input className="form-input" value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} />
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="is_active" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                <label htmlFor="is_active" className="text-sm">启用</label>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowForm(false)} className="btn-secondary">取消</button>
              <button onClick={handleSave} className="px-4 py-2 bg-primary text-white rounded-lg text-sm">保存</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
