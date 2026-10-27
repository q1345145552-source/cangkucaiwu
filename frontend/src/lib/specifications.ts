export type SpecValue = string | number | boolean | null | SpecValue[] | { [key: string]: SpecValue };
export type SpecAttributes = Record<string, SpecValue>;
export type SpecNode = {
  id: string;
  key: string;
  kind: 'text' | 'number' | 'boolean' | 'object' | 'array' | 'null';
  text: string;
  checked: boolean;
  children: SpecNode[];
};

let sequence = 0;
export const specLabels: Readonly<Record<string, string>> = Object.freeze(Object.assign(Object.create(null) as Record<string, string>, {
  material: '材质', width: '宽度', length: '长度', height: '高度', thickness: '厚度',
  weight: '重量', packaging: '包装说明', color: '颜色', value: '数值', unit: '单位',
}));

export function newSpecNode(key = '', kind: SpecNode['kind'] = 'text'): SpecNode {
  return { id: `spec-${++sequence}`, key, kind, text: '', checked: false, children: [] };
}

function nodeFromValue(key: string, value: SpecValue): SpecNode {
  const node = newSpecNode(key);
  if (value === null) return { ...node, kind: 'null' };
  if (Array.isArray(value)) return { ...node, kind: 'array', children: value.map((v, i) => nodeFromValue(String(i), v)) };
  if (typeof value === 'object') return { ...node, kind: 'object', children: Object.entries(value).map(([k, v]) => nodeFromValue(k, v)) };
  if (typeof value === 'boolean') return { ...node, kind: 'boolean', checked: value };
  return { ...node, kind: typeof value === 'number' ? 'number' : 'text', text: String(value) };
}

export function specDraft(value?: SpecAttributes | null): SpecNode[] {
  return value ? Object.entries(value).map(([key, item]) => nodeFromValue(key, item)) : [];
}

export function readSpecDraft(nodes: SpecNode[], required = false): SpecAttributes | null {
  if (!nodes.length) {
    if (required) throw Error('请至少填写一项已核实的产品规格');
    return null;
  }
  function values(rows: SpecNode[], path: string, list = false): SpecAttributes | SpecValue[] {
    const keys = new Set<string>();
    const entries = rows.map((node, index): [string, SpecValue] => {
      const key = list ? String(index) : node.key.trim();
      if (!key) throw Error(`${path}请填写规格名称`);
      if (keys.has(key)) throw Error(`${path}规格名称「${key}」重复`);
      keys.add(key);
      const label = `${path}${specLabels[key] || key}：`;
      let value: SpecValue;
      if (node.kind === 'object') value = values(node.children, label) as SpecAttributes;
      else if (node.kind === 'array') value = values(node.children, label, true) as SpecValue[];
      else if (node.kind === 'boolean') value = node.checked;
      else if (node.kind === 'null') value = null;
      else {
        if (!node.text.trim()) throw Error(`${label}请填写规格值，未知的项目可移除`);
        if (node.kind === 'number') {
          value = Number(node.text);
          if (!Number.isFinite(value)) throw Error(`${label}请输入有效数字`);
        } else value = node.text.trim();
      }
      return [key, value];
    });
    return list ? entries.map(([, value]) => value) : Object.fromEntries(entries);
  }
  return values(nodes, '') as SpecAttributes;
}

export function specDescription(value: SpecValue | undefined): string {
  if (value === undefined) return '尚未填写规格';
  if (value === null) return '空值（历史记录）';
  if (Array.isArray(value)) return value.map(specDescription).join('、') || '暂无项目';
  if (typeof value === 'object') {
    if ('value' in value && 'unit' in value && Object.keys(value).length === 2)
      return `${specDescription(value.value)} ${specDescription(value.unit)}`;
    return Object.entries(value).map(([key, item]) => `${specLabels[key] || key}：${specDescription(item)}`).join('；') || '尚未填写规格';
  }
  return typeof value === 'boolean' ? (value ? '是' : '否') : String(value);
}
