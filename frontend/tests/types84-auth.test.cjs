const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const root = path.resolve(__dirname, '../src');
function compile(file, imports = {}, globals = {}) {
  const m = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    fileName: file, compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText, { module: m, exports: m.exports, require: name => imports[name] || require(name), console, CustomEvent, Event, ...globals });
  return m.exports;
}
const authTypes = compile('types/auth.ts');
const roles = ['warehouse_admin', 'super_admin', 'supervisor', 'staff', 'warehouse_labor'];
function user(role = 'supervisor', id = 4) {
  return { id, username: 'synthetic-' + id, display_name: '测试账号', role, warehouse_id: 1, warehouse_name: '合成仓',
    warehouses: [{ id: 1, name: '合成仓', code: 'LOCAL' }], extra_permissions: ['供应商管理', '耗材库存'], is_active: true,
    attendance_enabled: role === 'supervisor', attendance_employee_id: role === 'supervisor' ? 20 : null };
}
for (const role of roles) assert(authTypes.isAuthUser(user(role)));
for (const bad of [null, [], {}, 'null', { ...user(), role: 'owner' }, { ...user(), id: 1.5 }, { ...user(), warehouse_id: '1' },
  { ...user(), warehouses: [{ id: 2, name: '缺编号' }] }, { ...user(), extra_permissions: [1] },
  { ...user(), attendance_enabled: 'false' }, { ...user(), attendance_employee_id: '20' }]) assert(!authTypes.isAuthUser(bad), JSON.stringify(bad));
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness({ cached, token: initialToken = null, serverUser = user() } = {}) {
  const local = new Map();
  if (cached !== undefined) local.set('user', typeof cached === 'string' ? cached : JSON.stringify(cached));
  let token = initialToken;
  if (token) local.set('token', token);
  const storage = { getItem: k => local.get(k) || null, setItem: (k, v) => local.set(k, String(v)), removeItem: k => local.delete(k) };
  const events = new EventTarget(), effects = [], cleanups = [], slots = [], calls = [], routes = [], published = [], reads = [], logouts = [];
  let index = 0, initialized = false, value = null, holdReads = false, holdLogout = false, failLogin = false, failCookie = false;
  let response = { ...user(), user_id: 4, access_token: 'synthetic-login-token', token_type: 'bearer' };
  events.addEventListener('auth-user-refreshed', event => published.push(event.detail));
  const react = { ...React,
    createContext: () => ({ Provider: 'auth-provider' }), useContext: () => value,
    useState(initial) { const i = index++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial; return [slots[i], next => { slots[i] = typeof next === 'function' ? next(slots[i]) : next; }]; },
    useRef(initial) { const i = index++; return slots[i] || (slots[i] = { current: initial }); },
    useEffect(fn) { if (!initialized) effects.push(fn); },
  };
  const api = {
    async get(route) { calls.push({ method: 'GET', route }); return holdReads ? new Promise((resolve, reject) => reads.push({ resolve, reject })) : serverUser; },
    async post(route, body) {
      calls.push({ method: 'POST', route, body });
      if (route === '/auth/login') { if (failLogin) throw Error('账号已被禁用'); return response; }
      if (holdLogout && body?.clear) return new Promise(resolve => logouts.push(resolve));
      if (failCookie) throw Error('附件会话清理失败');
      return { ok: true };
    },
  };
  const module = compile('hooks/useAuth.tsx', { react, 'next/navigation': { useRouter: () => ({ push: route => routes.push(route) }) },
    '@/types/auth': authTypes, '@/lib/api': { api, getToken: () => token, setToken: t => { token = t; storage.setItem('token', t); },
      clearToken: () => { token = null; for (const k of ['token', 'user', 'activeWarehouseId']) storage.removeItem(k); },
      setActiveWarehouseId: id => storage.setItem('activeWarehouseId', id) } }, { localStorage: storage, window: events });
  function render() { index = 0; const tree = module.AuthProvider({ children: 'child' }); value = tree.props.value; initialized = true; return value; }
  render(); effects.splice(0).forEach(fn => { const cleanup = fn(); if (cleanup) cleanups.push(cleanup); });
  return { render, get auth() { return module.useAuth(); }, outside() { value = null; return module.useAuth(); }, get token() { return token; },
    local, calls, routes, published, reads, logouts, setToken(t) { token = t; }, holdReads(v = true) { holdReads = v; }, holdLogout(v = true) { holdLogout = v; },
    event(detail) { events.dispatchEvent(new CustomEvent('auth-user-refreshed', { detail })); }, focus() { events.dispatchEvent(new Event('focus')); },
    permissionsChanged() { events.dispatchEvent(new Event('permissions-changed')); }, storage(key) { const e = new Event('storage'); e.key = key; events.dispatchEvent(e); },
    response(v) { response = v; }, server(v) { serverUser = v; }, failLogin() { failLogin = true; }, failLogout() { failCookie = true; },
    cleanup() { cleanups.forEach(fn => fn()); }, async flush() { await tick(); await tick(); return render(); },
    resolveRead(i, data) { reads[i].resolve(data); }, rejectRead(i) { reads[i].reject(Error('合成校验失败')); },
  };
}
const results = [];
async function check(name, run) { await run(); results.push(name); console.log('PASS', name); }
(async () => {
  await check('Ordinary focus preserves verified identity while validation is pending and on success', async () => {
    const h = harness({ token: 'valid-token', serverUser: user() }); await h.flush(); const identity = h.render().user;
    h.holdReads(); const before = h.published.filter(x => x === null).length; h.focus();
    assert.equal(h.render().user, identity, 'Focus must not clear the user and unmount the upload page');
    assert.equal(h.published.filter(x => x === null).length, before, 'Focus must not tell DashboardLayout to remove its children');
    h.resolveRead(0, { ...user() }); await h.flush(); assert.equal(h.render().user.id, 4);
    assert.equal(h.published.filter(x => x === null).length, before); assert(h.calls.some(x => x.route === '/auth/attachment-session'));
    h.cleanup();
  });
  await check('Initial cache is never authorization; live verification is required', async () => {
    for (const cached of [user(), '{broken', JSON.stringify({ ...user(), role: 'invalid' }), 'null']) {
      const h = harness({ cached, token: 'old-token' }); assert.equal(h.render().user, null); assert(h.auth.loading); assert(!h.auth.isAuthenticated);
      await h.flush(); assert.equal(h.render().user.id, 4); assert.equal(h.auth.loading, false); h.cleanup();
    }
    const h = harness({ cached: user() }); assert.equal(h.render().user, null); assert(!h.auth.isAuthenticated); h.cleanup();
  });
  await check('Live revocation, attendance disabling, malformed events, cleanup and context misuse remain covered', async () => {
    const h = harness({ token: 'valid-token' }); await h.flush(); const valid = user();
    h.event({ ...valid, extra_permissions: [] }); assert.deepEqual(h.render().user.extra_permissions, []);
    h.event({ ...valid, attendance_enabled: false, attendance_employee_id: null }); assert.equal(h.render().user.attendance_enabled, false);
    h.event({ ...valid, role: 'made-up-role' }); assert.equal(h.render().user.attendance_enabled, false);
    h.event(null); assert.equal(h.render().user, null); assert(!h.auth.isAuthenticated);
    h.cleanup(); h.event(valid); assert.equal(h.render().user, null); assert.throws(() => h.outside(), /AuthProvider/);
  });
  await check('All five roles retain login, employee redirect, attendance, warehouse and failed cookie-cleanup behavior', async () => {
    for (const role of roles) {
      const h = harness(); h.response({ ...user(role), user_id: 4, access_token: 'synthetic-login-token', token_type: 'bearer' });
      await h.auth.login('synthetic-user', 'synthetic-password'); const context = h.render();
      assert.equal(context.user.role, role); assert.equal(context.user.attendance_enabled, role === 'supervisor');
      assert.equal(h.local.get('activeWarehouseId'), '1'); assert.equal(JSON.parse(h.local.get('user')).role, role);
      assert.equal(h.routes.at(-1), role === 'warehouse_labor' ? '/clock-in' : '/dashboard');
      assert.equal(h.calls[0].route, '/auth/login'); h.failLogout(); await h.auth.logout();
      assert.equal(h.render().user, null); assert.equal(h.token, null); assert.equal(h.local.get('user'), undefined);
      assert.equal(h.local.get('activeWarehouseId'), undefined); assert.equal(h.routes.at(-1), '/login'); h.cleanup();
    }
    const h = harness(); h.failLogin(); await assert.rejects(() => h.auth.login('synthetic-user', 'wrong'), /账号已被禁用/);
    assert.equal(h.render().user, null); assert.equal(h.token, null); assert.equal(h.routes.length, 0); h.cleanup();
  });
  await check('Explicit permission changes invalidate immediately and stale focus responses cannot restore grants', async () => {
    const h = harness({ token: 'valid-token' }); await h.flush(); h.holdReads(); h.focus(); h.permissionsChanged();
    assert.equal(h.render().user, null); h.resolveRead(0, user()); await h.flush(); assert.equal(h.render().user, null);
    h.resolveRead(1, { ...user(), extra_permissions: [] }); await h.flush(); assert.deepEqual(h.render().user.extra_permissions, []); h.cleanup();
  });
  await check('Fresh focus response replaces permissions; removed grants never survive the new response', async () => {
    const h = harness({ token: 'valid-token' }); await h.flush(); h.holdReads(); h.focus();
    h.resolveRead(0, { ...user(), extra_permissions: [], attendance_enabled: false }); await h.flush();
    assert.deepEqual(h.render().user.extra_permissions, []); assert.equal(h.render().user.attendance_enabled, false); h.cleanup();
  });
  await check('Concurrent refreshes use only the newest response', async () => {
    const h = harness({ token: 'valid-token' }); await h.flush(); h.holdReads(); h.focus(); h.focus();
    h.resolveRead(1, { ...user(), extra_permissions: [] }); await h.flush(); h.resolveRead(0, user()); await h.flush();
    assert.deepEqual(h.render().user.extra_permissions, []); h.cleanup();
  });
  await check('A failed newest check cannot be undone by an older successful request', async () => {
    const h = harness({ token: 'valid-token' }); await h.flush(); h.holdReads(); h.focus(); h.focus();
    h.rejectRead(1); await h.flush(); assert.equal(h.render().user, null); assert.equal(h.published.at(-1), null);
    h.resolveRead(0, user()); await h.flush(); assert.equal(h.render().user, null); h.cleanup();
  });
  await check('Disabled users, malformed responses and cookie-session failures fail closed', async () => {
    for (const invalid of [{ ...user(), is_active: false }, { ...user(), role: 'invalid' }, null]) {
      const h = harness({ token: 'valid-token' }); await h.flush(); h.holdReads(); h.focus(); h.resolveRead(0, invalid); await h.flush();
      assert.equal(h.render().user, null); assert.equal(h.published.at(-1), null); h.cleanup();
    }
    const h = harness({ token: 'valid-token' }); await h.flush(); h.failLogout(); h.focus(); await h.flush();
    assert.equal(h.render().user, null); assert.equal(h.published.at(-1), null); h.cleanup();
  });
  await check('Storage token replacement and removal clear old identity and reject old-token responses', async () => {
    const h = harness({ token: 'old-token' }); await h.flush(); h.holdReads(); h.focus(); h.setToken('new-token'); h.storage('token');
    assert.equal(h.render().user, null); h.resolveRead(0, user()); await h.flush(); assert.equal(h.render().user, null);
    h.resolveRead(1, user('staff', 8)); await h.flush(); assert.equal(h.render().user.id, 8);
    h.setToken(null); h.storage('token'); assert.equal(h.render().user, null); h.cleanup();
  });
  await check('Logout cannot be reversed by an outstanding identity request', async () => {
    const h = harness({ token: 'valid-token' }); await h.flush(); h.holdReads(); h.focus(); await h.auth.logout();
    h.resolveRead(0, user()); await h.flush(); assert.equal(h.render().user, null); assert.equal(h.token, null); h.cleanup();
  });
  await check('Old logout completion cannot clear a newly logged-in account', async () => {
    const h = harness({ token: 'valid-token' }); await h.flush(); h.holdLogout(); const oldLogout = h.auth.logout();
    h.response({ ...user('staff', 8), user_id: 8, access_token: 'new-login-token', token_type: 'bearer' }); await h.auth.login('new', 'synthetic');
    h.logouts[0]({ ok: true }); await oldLogout;
    assert.equal(h.render().user.id, 8); assert.equal(h.token, 'new-login-token'); assert.equal(h.routes.at(-1), '/dashboard'); h.cleanup();
  });
  await check('External revocation and provider unmount reject requests already in flight', async () => {
    for (const action of ['revoke', 'unmount']) {
      const h = harness({ token: 'valid-token' }); await h.flush(); h.holdReads(); h.focus();
      if (action === 'revoke') h.event(null); else h.cleanup();
      h.resolveRead(0, { ...user(), extra_permissions: [] }); await h.flush();
      if (action === 'revoke') assert.equal(h.render().user, null); else assert.deepEqual(h.render().user.extra_permissions, user().extra_permissions);
      h.cleanup();
    }
  });
  console.log(JSON.stringify({ passed: results.length, checks: results }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
