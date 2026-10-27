'use client';
import { newSpecNode, specDescription, specLabels, type SpecNode, type SpecValue } from '@/lib/specifications';

const kinds: { value: SpecNode['kind']; label: string }[] = [
  { value: 'text', label: '文字' }, { value: 'number', label: '数字' },
  { value: 'boolean', label: '是 / 否' }, { value: 'object', label: '分组规格' },
  { value: 'array', label: '多项规格' }, { value: 'null', label: '历史空值' },
];

export function SpecificationSummary({ value }: { value?: SpecValue }) {
  return <p className="text-sm break-words text-gray-600">{specDescription(value)}</p>;
}

export default function StructuredSpecifications({ value, onChange, disabled = false, label = '产品规格' }: {
  value: SpecNode[]; onChange: (value: SpecNode[]) => void; disabled?: boolean; label?: string;
}) {
  function rows(nodes: SpecNode[], update: (next: SpecNode[]) => void, path: string, list = false, depth = 0) {
    function change(index: number, patch: Partial<SpecNode>) {
      update(nodes.map((node, i) => i === index ? { ...node, ...patch } : node));
    }
    return <div className="space-y-3">
      {nodes.map((node, index) => {
        const name = `${path}第${index + 1}项`;
        return <div key={node.id} className="border rounded-lg p-3 space-y-2 min-w-0">
          <div className="flex flex-wrap gap-2 items-end">
            {!list && <label className="flex-1 min-w-[120px] text-sm">规格名称<input className="form-input" aria-label={`${name}名称`} disabled={disabled} value={specLabels[node.key] || node.key} placeholder="例如材质、宽度或自定义名称" onChange={e => change(index, { key: Object.keys(specLabels).find(key => specLabels[key] === e.target.value) || e.target.value })} /></label>}
            {specLabels[node.key] && <span className="text-sm text-gray-600">{specLabels[node.key]}</span>}
            <label className="text-sm">填写方式<select className="form-input" aria-label={`${name}填写方式`} value={node.kind} disabled={disabled} onChange={e => change(index, { kind: e.target.value as SpecNode['kind'] })}>
              {kinds.map(kind => <option key={kind.value} value={kind.value}>{kind.label}</option>)}
            </select></label>
            <button type="button" className="text-sm text-red-700 px-2 py-2" disabled={disabled} onClick={() => update(nodes.filter((_, i) => i !== index))}>移除{name}</button>
          </div>
          {node.kind === 'text' || node.kind === 'number' ? <label className="block text-sm">{node.kind === 'number' ? '数值' : '规格内容'}<input aria-label={`${name}值`} className="form-input" disabled={disabled} type={node.kind === 'number' ? 'number' : 'text'} step="any" value={node.text} onChange={e => change(index, { text: e.target.value })} /></label>
            : node.kind === 'boolean' ? <label className="flex gap-2 items-center text-sm"><input type="checkbox" aria-label={`${name}值`} disabled={disabled} checked={node.checked} onChange={e => change(index, { checked: e.target.checked })} />是（不勾选表示否）</label>
              : node.kind === 'null' ? <p className="text-sm text-amber-700">保留历史空值；如需补充，请选择填写方式后填写。</p>
                : <div className="pl-2 border-l">{rows(node.children, next => change(index, { children: next }), `${name}的`, node.kind === 'array', depth + 1)}</div>}
        </div>;
      })}
      {depth < 4 && <button type="button" className="btn-secondary text-sm" disabled={disabled} onClick={() => update([...nodes, newSpecNode()])}>添加{path || '其他'}规格</button>}
    </div>;
  }
  function add(key: string, dimension = false) {
    const node = newSpecNode(key, dimension ? 'object' : 'text');
    if (dimension) node.children = [newSpecNode('value', 'number'), newSpecNode('unit')];
    onChange([...value, node]);
  }
  return <fieldset className="space-y-3 min-w-0" disabled={disabled}>
    <legend className="font-medium text-sm mb-2">{label}</legend>
    <div className="flex flex-wrap gap-2">{[['material', '添加材质'], ['width', '添加宽度'], ['length', '添加长度'], ['packaging', '添加包装说明']].map(([key, text]) => <button key={key} type="button" className="btn-secondary text-sm" disabled={disabled || value.some(node => node.key === key)} onClick={() => add(key, key === 'width' || key === 'length')}>{text}</button>)}</div>
    {!value.length && <p className="text-sm text-gray-600">填写已核实的材质、尺寸或包装；未知项目可留空，不会自动推断换算。</p>}
    {rows(value, onChange, label)}
  </fieldset>;
}
