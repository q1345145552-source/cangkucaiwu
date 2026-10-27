// Execute the original shared payment form and the separate review page callbacks.
// Shared identity UI and real request/file transport are tested in supplier-cost-identity-round4.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const ts = require('typescript'), React = require('react');
const walk = x => !x || typeof x !== 'object' ? [] : Array.isArray(x) ? x.flatMap(walk) : [x, ...walk(x.props?.children)];
const text = x => x == null || typeof x === 'boolean' ? '' : typeof x !== 'object' ? String(x) : Array.isArray(x) ? x.map(text).join('') : text(x.props?.children);
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
function hooks() {
  const state = [], refs = [], deps = []; let si = 0, ri = 0, ei = 0, effects = [];
  return { react: { ...React,
    useState(v) { const i = si++; if (!(i in state)) state[i] = typeof v === 'function' ? v() : v; return [state[i], v => state[i] = typeof v === 'function' ? v(state[i]) : v]; },
    useRef(v) { const i = ri++; return refs[i] ||= { current: v }; },
    useEffect(fn, d) { const i = ei++, next = JSON.stringify(d); if (deps[i] !== next) { deps[i] = next; effects.push(fn); } },
  }, async render(component) { for (let i = 0; i < 12; i++) { si = ri = ei = 0; const tree = component(); if (!effects.length) { await tick(); si = ri = ei = 0; return component(); } const pending = effects; effects = []; pending.forEach(fn => fn()); await tick(); } throw Error('effects did not settle'); } };
}
function load(file, h, overrides) {
  const m = { exports: {} }, api = overrides['@/lib/api'];
  const defaults = { react: h.react, '@/lib/balanceWarning':require('./balance-warning-test-support.cjs'), '@/lib/api': api, '@/lib/currency': { fmtMoney: String, fmtMoneyByCurrency: () => '' },
    '@/components/common/DataTable': { __esModule: true, default: 'DataTable' }, '@/components/InternalTransferSummary': { __esModule: true, default: 'TransferSummary' },
    '@/hooks/useAuth': { useAuth: () => ({ user: { id: 1, role: 'warehouse_admin' } }) }, '@/hooks/useI18n': { useI18n: () => ({ t: x => x }) },
    '@/components/ui/Toast': { useToast: () => ({ toast() {} }) }, 'next/navigation': { useRouter: () => ({ push() {} }) },
    'lucide-react': new Proxy({}, { get: (_, key) => String(key) }) };
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src', file), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  vm.runInNewContext(code, { module: m, exports: m.exports, require: name => overrides[name] || defaults[name] || require(name), console, URLSearchParams, Date, Intl, process: { env: {} } }); return m.exports.default;
}
const button = (tree, label) => { const node = walk(tree).find(x => x.type === 'button' && text(x) === label); assert(node, 'missing ' + label); return node; };
const empty = () => ({ supplier_id: 0, invoice: { issuer_identifier: '', series: '', number: '', verified: false } });
(async () => {
  let retry, captured = [], resets = [], walletCalls = [], pending = null;
  const invoice = { issuer_identifier: 'TAX', series: 'VAT', number: 'DISTINCT', verified: true };
  const cost = { fields: 'ACTUAL-COST-FIELDS', dialog: 'COST-DIALOG', reset(v) { resets.push(v); }, payload: () => ({ supplier_id: 1, invoice_identity: invoice }),
    capture(error, fn) { if (!error.detail?.code?.startsWith('cost_')) return false; captured.push(error.detail); retry = fn; return true; } };
  const api = { getToken: () => 'synthetic', getActiveWarehouseId: () => '1', api: { get: async url => url.includes('monthly-summary') ? {} : { data: [], total: 0 } } };
  const h = hooks(), Payment = load('app/(dashboard)/income-expense/page.tsx', h, { '@/lib/api': api,
    '@/components/CostIdentity': { useCostIdentity: () => cost, emptyCost: empty },
    '@/lib/manualWallet': { pendingWalletOperation: () => pending, submitWalletOperation: async (...args) => { walletCalls.push(args); if (!args[3]) throw { detail: { code: 'cost_duplicate_confirmation', version: 'current' } }; return { id: 9 }; } } });
  let tree = await h.render(Payment); await button(tree, '付款').props.onClick(); tree = await h.render(Payment);
  await button(tree, '新建记录').props.onClick(); tree = await h.render(Payment); assert(text(tree).includes('ACTUAL-COST-FIELDS'));
  await button(tree, '保存').props.onClick(); assert.equal(captured.length, 1); assert.equal(walletCalls[0][0], 'expense'); assert.equal(walletCalls[0][1].supplier_id, 1); assert.equal(walletCalls[0][1].invoice_identity.number, 'DISTINCT');
  const confirm = { candidate_refs: ['payable:2'], version: 'current', reason: '独立原票', target_ref: 'expense:9' }; await retry(confirm); assert.equal(walletCalls[1][3], confirm);
  pending = { payload: { category_id: 1, account_id: 1, amount: 100, currency: 'THB', expense_date: '2026-10-26', supplier_id: 1, invoice_identity: JSON.stringify(invoice) } };
  tree = await h.render(Payment); await button(tree, '新建记录').props.onClick(); assert.equal(resets.at(-1).invoice.number, 'DISTINCT');
  let posts = [], single = false;
  api.api.get = async url => ({ data: url.includes('/review/pending') ? [{ id: 9, amount: 100, currency: 'THB' }, { id: 10, amount: 100, currency: 'THB' }] : [{ employee_id: 4, employee_name: '合成人员' }] });
  api.api.post = async (url, body) => { posts.push(body); const missing = single ? !body.cost_confirmation && 9 : [9, 10].find(id => !body.cost_confirmations?.[id]); if (missing) throw { detail: { code: 'cost_duplicate_confirmation', target_ref: 'fund_item:' + missing } }; return {}; };
  const reviewHooks = hooks(), Review = load('app/(dashboard)/fund-review/page.tsx', reviewHooks, { '@/lib/api': api, '@/components/CostIdentity': { useCostIdentity: () => cost } });
  tree = await reviewHooks.render(Review); walk(tree).find(x => x.type === 'input' && x.props.type === 'checkbox').props.onChange(); tree = await reviewHooks.render(Review);
  const batch = walk(tree).find(x => x.type === 'button' && text(x).includes('通过所选')); assert(batch); await batch.props.onClick();
  await retry({ ...confirm, target_ref: 'fund_item:9' }); await retry({ ...confirm, target_ref: 'fund_item:10' });
  assert.equal(posts.length, 3); assert(posts[2].cost_confirmations[9]); assert(posts[2].cost_confirmations[10]); assert.deepEqual(Array.from(posts[2].item_ids), [9, 10]);
  single = true; tree = await reviewHooks.render(Review); await walk(tree).find(x => x.type === 'button' && x.props.title === '通过').props.onClick(); await retry({ ...confirm, target_ref: 'fund_item:9' });
  assert.equal(posts.at(-1).cost_confirmation.target_ref, 'fund_item:9'); assert.deepEqual(Array.from(posts.at(-1).item_ids), [9]);
  console.log('PASS: original shared expense form supplies/restores invoice and structured retry; separate review page retains per-item batch confirmations and single-item confirmation without changing original IDs/actions');
})().catch(error => { console.error(error); process.exitCode = 1; });
