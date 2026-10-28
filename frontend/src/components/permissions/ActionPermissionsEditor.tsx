"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ActionAccess } from "@/types/auth";
import type { ActionTier } from "@/hooks/useActionPermission";
interface TierDescription { grant: string; allowed: boolean; reason: string; actions: { id: string; label: string; method: string[]; path: string; roles: string[] }[] }
interface ModuleDescription { key: string; label: string; tiers: Record<ActionTier, TierDescription>; minimum_read: string }
interface Props {
  role: string; selected: string[]; onChange: (grants: string[]) => void;
  reason: string; onReasonChange: (value: string) => void; previous?: ActionAccess;
  onLoadingChange: (loading: boolean) => void; onErrorChange: (error: string) => void;
}
const tiers: [ActionTier, string][] = [["view", "查看"], ["operate", "操作"], ["approve", "审批"]];
export default function ActionPermissionsEditor({ role, selected, onChange, reason, onReasonChange, previous, onLoadingChange, onErrorChange }: Props) {
  const [modules, setModules] = useState<ModuleDescription[]>([]);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true; setModules([]); setError(""); onLoadingChange(true); onErrorChange("");
    api.get<{ modules: ModuleDescription[] }>(`/access/catalog?role=${encodeURIComponent(role)}`)
      .then(data => { if (active) setModules(data.modules); })
      .catch((err: unknown) => { if (active) { const text = err instanceof Error ? err.message : "权限清单加载失败"; setError(text); onErrorChange(text); } })
      .finally(() => { if (active) onLoadingChange(false); });
    return () => { active = false; };
  }, [role, revision, onLoadingChange, onErrorChange]);
  if (error) return <p role="alert" className="text-red-600">{error} <button type="button" onClick={() => setRevision(v => v + 1)}>重试</button></p>;
  if (!modules.length) return <p role="status">正在读取岗位动作权限…</p>;
  const invalid = selected.filter(grant => !modules.some(m => tiers.some(([tier]) => m.tiers[tier].grant === grant && m.tiers[tier].allowed)));
  return <div className="space-y-3" aria-label="三档动作权限">
    {previous?.version === "invalid" && <p role="alert" className="text-red-600">当前权限版本或内容有冲突，管理动作已拒绝。请根据岗位逐项重新选择并填写核对原因；不会自动恢复历史全权限。</p>}
    {previous?.version === "legacy" && <p className="text-sm text-amber-800 bg-amber-50 p-2">历史菜单已按当前角色换算供核对；保存后才转换为三档权限。未识别旧值：{previous.unknown_legacy_values.join("、") || "无"}。</p>}
    <p className="text-xs text-gray-600">三档独立授权。操作不等于审批，也不自动取得全部查看权限；必要选择器只提供编号、名称和状态。仓库、本人隔离及业务状态仍独立校验。</p>
    {!!invalid.length && <p role="alert" className="text-red-600">以下旧选择不适用于当前角色：{invalid.join("、")}。<button type="button" onClick={() => onChange(selected.filter(g => !invalid.includes(g)))} className="underline">移除超范围选择</button></p>}
    <div className="max-h-80 overflow-auto border rounded">
      <table className="w-full text-sm"><thead className="sticky top-0 bg-white"><tr><th className="p-2 text-left">模块</th>{tiers.map(([tier, label]) => <th key={tier} className="p-2">{label}</th>)}</tr></thead>
        <tbody>{modules.filter(m => tiers.some(([tier]) => m.tiers[tier].actions.length)).map(module => <tr key={module.key} className="border-t">
          <th className="p-2 text-left font-normal">{module.label}<details className="text-xs font-normal text-gray-500"><summary>动作与范围</summary>{tiers.map(([tier, label]) => <div key={tier}><strong>{label}</strong><ul>{module.tiers[tier].actions.map(a => <li key={a.id}>{a.label} {a.roles.includes(role) ? "" : "（超出角色上限）"}</li>)}</ul></div>)}<p>{module.minimum_read}</p></details></th>
          {tiers.map(([tier, label]) => { const item = module.tiers[tier]; return <td key={tier} className="p-2 text-center"><label className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center" title={item.reason}><input type="checkbox" aria-label={`${module.label} ${label}`} disabled={!item.allowed} checked={selected.includes(item.grant)} onChange={() => onChange(selected.includes(item.grant) ? selected.filter(g => g !== item.grant) : [...selected, item.grant])} /></label>{!item.allowed && <span className="block text-xs text-gray-400">超出职责或无该动作</span>}</td>; })}
        </tr>)}</tbody></table>
    </div>
    <label className="block text-sm">调整原因<input aria-label="权限调整原因" className="form-input mt-1" maxLength={200} value={reason} onChange={e => onReasonChange(e.target.value)} placeholder="说明本次授权或撤回的原因" required /></label>
  </div>;
}
