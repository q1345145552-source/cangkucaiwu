// Actual production frontend with synthetic transport only; no production access.
// Usage: NODE_PATH=/path/to/playwright node upload-form-state.browser.cjs state.json
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require('playwright');
const state = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const web = `http://127.0.0.1:${state.port}`, out = state.evidence;
assert(state.port > 1024 && ![18080, 18082].includes(state.port));
const png = { name: '合成凭证.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aStsAAAAASUVORK5CYII=', 'base64') };
const actions = ['expense_fund.add_item', 'suppliers.import_products_for_supplier', 'suppliers.upload_purchase_receipt', 'suppliers.import_products'];
function identity(role) {
  return { id: 1, username: 'synthetic-upload', display_name: '合成测试账号', role, warehouse_id: 1,
    warehouse_name: '合成测试仓', warehouses: [1, 2].map(id => ({ id, name: `合成测试仓${id}`, code: `LOCAL${id}` })),
    extra_permissions: ['供应商管理', '备用金管理'], is_active: true, attendance_enabled: false, attendance_employee_id: null,
    action_access: { version: 1, grants: ['suppliers:operate', 'expense_fund:operate'],
      actions: actions.map(id => ({ id, module: id.startsWith('expense') ? 'expense_fund' : 'suppliers', tier: 'operate' })),
      unknown_legacy_values: [], compatibility_note: '' } };
}
const suppliers = [1, 2].map(id => ({ id, name: `合成供应商${id}`, category_id: 1, category_name: '耗材商', default_currency: 'THB' }));
const order = { id: 11, order_number: 'PO-SYNTH-11', supplier_id: 1, supplier_name: suppliers[0].name,
  warehouse_name: '合成测试仓', total_amount: 100, currency: 'THB', status: 'confirmed', flow_status: 'sent',
  receipt_status: 'not_received', items: [], receipt_events: [] };
const contract = { id: actions[1], module_key: 'suppliers', tier: 'operate', mode: 'business',
  form: { label: '合成文件办理', method: 'POST', path: '/suppliers/{supplier_id}/import/products',
    parameters: [{ name: 'supplier_id', in: 'path', required: true, schema: { type: 'integer' } }],
    media: 'multipart/form-data', body: { type: 'object', properties: { file: { type: 'string', format: 'binary' },
      description: { type: 'string' }, request_key: { type: 'string' } }, required: ['file'] } } };
const results = [], errors = [], requests = [];
let browser, current;
function record(name, details = {}) {
  results.push({ name, ...details });
  fs.writeFileSync(path.join(out, 'browser-results.json'), JSON.stringify({ synthetic_transport: true, results, errors, requests }, null, 2));
  console.log('PASS', name, JSON.stringify(details));
}
async function fixture(role, pathname, width = 1440) {
  const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 1000 } });
  context.setDefaultTimeout(10000);
  let who = identity(role), checks = 0, catalogReads = 0, failNext = false;
  const writes = [];
  await context.addInitScript(user => {
    localStorage.setItem('token', 'synthetic-upload-token'); localStorage.setItem('activeWarehouseId', '1');
    localStorage.setItem('user', JSON.stringify(user));
  }, who);
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.hostname !== '127.0.0.1') return route.abort();
    if (!url.pathname.startsWith('/api/v1/')) return route.continue();
    const endpoint = url.pathname.slice(7), method = request.method();
    let data = { data: [], total: 0 }, status = 200;
    if (endpoint === '/auth/me') { checks++; data = who; }
    else if (endpoint === '/auth/attachment-session') data = { ok: true };
    else if (endpoint === '/users/permissions') data = [
      { menu_key: 'suppliers', label: '供应商管理', path: '/suppliers', roles: ['warehouse_admin', 'staff', 'supervisor'], selectable: true },
      { menu_key: 'expense_fund', label: '备用金管理', path: '/expense-fund', roles: ['warehouse_admin', 'staff', 'supervisor'], selectable: true },
    ];
    else if (endpoint === '/expense-fund/accounts') data = { data: [{ id: 1, employee_id: 1, employee_name: '合成备用金账户',
      currency: 'THB', total_topped_up: 10000, current_balance: 10000, available: 10000, fund_limit: 10000, can_record: true }] };
    else if (endpoint === '/access/catalog') { catalogReads++; data = { routes: [contract] }; }
    else if (endpoint === '/suppliers') data = { data: suppliers, total: suppliers.length };
    else if (endpoint === '/suppliers/categories') data = { data: [{ id: 1, name: '耗材商' }] };
    else if (endpoint === '/suppliers/purchase-orders') data = { data: [order], total: 1 };
    else if (endpoint === '/suppliers/purchase-orders/11') data = order;
    else if (method === 'POST') {
      const fields = {};
      if (request.headers()['content-type']?.startsWith('multipart/form-data')) {
        const form = await new Response(request.postDataBuffer(), { headers: { 'content-type': request.headers()['content-type'] } }).formData();
        for (const [name, value] of form) fields[name] = typeof value === 'string' ? value : { name: value.name, size: value.size, type: value.type };
      } else if (request.postData()) Object.assign(fields, JSON.parse(request.postData()));
      const written = { endpoint, method, fields, warehouse: request.headers()['x-warehouse-id'] };
      writes.push(written); requests.push(written);
      if (failNext) { failNext = false; status = 500; data = { detail: '合成上传失败，请重试' }; }
      else if (endpoint.includes('/import/products') && fields.mode === 'preview') {
        const batch = endpoint === '/suppliers/import/products', count = batch ? 2 : 1;
        data = { mode: 'preview', valid: true, total_rows: count, valid_count: count, skipped_count: 0, skipped_rows: [], errors: [],
          message: '合成预览，尚未写入', preview_version: 'synthetic-preview-version',
          rows: suppliers.slice(0, count).map((s, i) => ({ row_number: i + 2, supplier_id: s.id, supplier_name: s.name,
            product_name: `合成产品${s.id}`, unit_price: 10, currency: 'THB', unit: '个', spec: '合成规格', candidates: [], errors: [], warnings: [], skipped: false })) };
      } else if (endpoint.includes('/import/products') && fields.mode === 'confirm') data = { id: 91, mode: 'confirmed', imported: 2, skipped: 0, updated: 0, errors: [], message: '导入成功 2 条，跳过 0 条，更新 0 条' };
      else if (endpoint.endsWith('/upload-receipt')) data = { receipt: '/uploads/synthetic-receipt.png' };
      else data = { id: 91, message: '合成保存成功' };
    }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
  });
  const page = await context.newPage(); current = page;
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(web + pathname); await page.locator('#app-splash').waitFor({ state: 'hidden' });
  await page.waitForTimeout(250);
  await (await context.newCDPSession(page)).send('Emulation.setFocusEmulationEnabled', { enabled: false });
  const other = await context.newPage(); await page.bringToFront(); await page.waitForTimeout(200);
  return { page, context, writes, get catalogReads() { return catalogReads; },
    mutate(fn) { who = fn(who); }, failNext() { failNext = true; },
    async focus() { const before = checks; await other.bringToFront(); await page.waitForTimeout(100); await page.bringToFront();
      for (let n = 0; n < 100 && checks === before; n++) await page.waitForTimeout(30);
      assert(checks > before, 'Real tab return must refresh the identity'); await page.waitForTimeout(250); },
    async warehouse(id) { await page.evaluate(id => { localStorage.setItem('activeWarehouseId', id); window.dispatchEvent(new Event('warehouse-changed')); }, String(id)); },
  };
}
(async () => {
  browser = await chromium.launch({ headless: false, executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
  let h = await fixture('warehouse_admin', '/expense-fund');
  await h.page.getByRole('button', { name: '开销', exact: true }).click();
  let modal = h.page.getByRole('dialog', { name: '添加备用金开销', exact: true });
  await modal.locator('input[type=number]').fill('200'); await modal.locator('#receiptFileInput4').setInputFiles(png);
  for (let n = 0; n < 3; n++) await h.focus();
  assert(await modal.isVisible()); assert.equal(await modal.locator('input[type=number]').inputValue(), '200');
  assert.equal(await modal.locator('#receiptFileInput4').evaluate(e => e.files[0].name), png.name);
  await h.page.screenshot({ path: path.join(out, '01-备用金-连续切窗后表单和凭证保留.png') });
  record('备用金连续切窗3次，金额和凭证保留');
  await h.warehouse(2); await modal.waitFor({ state: 'hidden' }); record('备用金真实切仓仍清空旧弹框');
  await h.context.close();
  for (const role of ['staff', 'supervisor']) {
    h = await fixture(role, '/suppliers', role === 'supervisor' ? 390 : 1440);
    const workspace = h.page.locator('section').filter({ has: h.page.getByRole('heading', { name: '办理事项', exact: true }) });
    await workspace.locator('select').first().selectOption(actions[1]);
    await workspace.getByLabel('供应商', { exact: true }).fill('1');
    await workspace.getByLabel('说明', { exact: true }).fill('合成说明必须保留');
    await workspace.locator('input[type=file]').setInputFiles(png);
    const reads = h.catalogReads; await h.focus(); await h.focus();
    assert.equal(h.catalogReads, reads, 'Unchanged grants must not reload the contract and regenerate the request key');
    assert.equal(await workspace.locator('select').first().inputValue(), actions[1]);
    assert.equal(await workspace.getByLabel('说明', { exact: true }).inputValue(), '合成说明必须保留');
    assert.equal(await workspace.locator('input[type=file]').evaluate(e => e.files[0].name), png.name);
    h.failNext(); await workspace.getByRole('button', { name: '确认提交', exact: true }).click();
    await workspace.getByRole('status').filter({ hasText: '合成上传失败，请重试' }).waitFor();
    const failed = h.writes.at(-1); assert(failed.fields.request_key);
    await h.focus(); await workspace.getByRole('button', { name: '确认提交', exact: true }).click();
    await workspace.getByRole('status').filter({ hasText: '合成保存成功' }).waitFor();
    assert.equal(h.writes.at(-1).fields.request_key, failed.fields.request_key);
    assert.deepEqual(h.writes.at(-1).fields, failed.fields);
    assert.equal(h.writes.at(-1).endpoint, '/suppliers/1/import/products');
    record(`${role}办理事项保留文件和输入，失败重试沿用原请求`, { width: role === 'supervisor' ? 390 : 1440, catalog_reads: reads });
    await workspace.locator('select').first().selectOption(actions[1]); await workspace.locator('input[type=file]').setInputFiles(png);
    h.mutate(u => ({ ...u, action_access: { ...u.action_access, grants: [], actions: [] } })); await h.focus();
    assert.equal(await workspace.locator('input[type=file]').count(), 0);
    assert.equal(await workspace.locator('select').first().inputValue(), '');
    record(`${role}撤销授权仍清空旧文件和事项`); await h.context.close();
  }
  h = await fixture('staff', '/suppliers');
  let workspace = h.page.locator('section').filter({ has: h.page.getByRole('heading', { name: '办理事项', exact: true }) });
  await workspace.locator('select').first().selectOption(actions[1]); await workspace.locator('input[type=file]').setInputFiles(png);
  await h.warehouse(2); await workspace.locator('input[type=file]').waitFor({ state: 'detached' });
  record('办理事项真实切仓仍清空旧表单'); await h.context.close();
  h = await fixture('staff', '/suppliers');
  workspace = h.page.locator('section').filter({ has: h.page.getByRole('heading', { name: '办理事项', exact: true }) });
  await workspace.locator('select').first().selectOption(actions[1]); await workspace.locator('input[type=file]').setInputFiles(png);
  h.mutate(u => ({ ...u, id: 8, username: 'another-synthetic-user' })); await h.focus();
  assert.equal(await workspace.locator('input[type=file]').count(), 0); record('办理事项换账号仍清空旧文件'); await h.context.close();
  h = await fixture('warehouse_admin', '/suppliers');
  await h.page.evaluate(() => {
    window.__pickers = [];
    const original = HTMLInputElement.prototype.showPicker;
    HTMLInputElement.prototype.showPicker = function () { window.__pickers.push({ label: this.getAttribute('aria-label'), click: window.event?.type === 'click' }); return original.call(this); };
  });
  let [chooser] = await Promise.all([h.page.waitForEvent('filechooser'), h.page.getByRole('row').filter({ has: h.page.getByRole('cell', { name: suppliers[0].name, exact: true }) }).getByTitle('导入产品', { exact: true }).click()]);
  await chooser.setFiles(state.product_file);
  modal = h.page.getByRole('dialog', { name: '产品Excel预览与确认', exact: true });
  await modal.getByRole('button', { name: '确认导入 1 条', exact: true }).waitFor();
  assert.equal(h.writes.at(-1).endpoint, '/suppliers/1/import/products');
  await modal.getByRole('button', { name: '关闭', exact: true }).click();
  [chooser] = await Promise.all([h.page.waitForEvent('filechooser'), h.page.getByRole('button', { name: '多供应商耗材导入', exact: true }).click()]);
  await chooser.setFiles(state.batch_file);
  await modal.getByRole('button', { name: '确认导入 2 条', exact: true }).waitFor();
  assert.equal(h.writes.at(-1).endpoint, '/suppliers/import/products', 'Batch import must clear the previous single-supplier target');
  await modal.getByRole('checkbox').check(); await h.focus(); assert(await modal.getByRole('checkbox').isChecked());
  await modal.getByRole('button', { name: '确认导入 2 条', exact: true }).click(); await modal.waitFor({ state: 'hidden' });
  assert.equal(h.writes.at(-1).fields.mode, 'confirm'); assert.equal(h.writes.at(-1).endpoint, '/suppliers/import/products');
  let pickerCalls = await h.page.evaluate(() => window.__pickers); assert(pickerCalls.every(p => p.click));
  record('单供应商切多供应商入口，点击内直接弹框且请求目标正确');
  await h.page.getByRole('button', { name: '采购单列表', exact: true }).click();
  await h.page.getByRole('row').filter({ hasText: order.order_number }).getByRole('button', { name: '明细', exact: true }).click();
  await h.page.getByRole('button', { name: '上传回执', exact: true }).waitFor();
  [chooser] = await Promise.all([h.page.waitForEvent('filechooser'), h.page.getByRole('button', { name: '上传回执', exact: true }).click()]);
  await chooser.setFiles(png); await h.page.getByText('回执已上传，供应商已确认', { exact: true }).waitFor();
  assert.equal(h.writes.at(-1).endpoint, '/suppliers/purchase-orders/11/receipt');
  assert.equal(h.writes.at(-1).fields.file.name, png.name); assert.equal(h.writes.at(-1).warehouse, '1');
  pickerCalls = await h.page.evaluate(() => window.__pickers); assert(pickerCalls.at(-1).click);
  record('采购回执点击内直接弹框，原单号和仓库头保留');
  await h.page.evaluate(() => Object.defineProperty(document.querySelector('input[aria-label="上传采购回执"]'), 'showPicker', { configurable: true, value() { throw new DOMException('synthetic block', 'NotAllowedError'); } }));
  await h.page.getByRole('button', { name: '上传回执', exact: true }).click(); await h.page.getByText('浏览器拦截了请重试', { exact: true }).waitFor();
  await h.page.evaluate(() => Object.defineProperty(document.querySelector('input[aria-label="上传采购回执"]'), 'showPicker', { configurable: true, value: undefined }));
  [chooser] = await Promise.all([h.page.waitForEvent('filechooser'), h.page.getByRole('button', { name: '上传回执', exact: true }).click()]); await chooser.setFiles(png);
  await h.page.getByText('回执已上传，供应商已确认', { exact: true }).last().waitFor();
  record('采购回执被浏览器拦截有提示，旧浏览器回退及同文件重选正常');
  await h.context.close();
  h = await fixture('warehouse_admin', '/expense-fund', 390);
  await h.page.getByRole('button', { name: '开销', exact: true }).click();
  modal = h.page.getByRole('dialog', { name: '添加备用金开销', exact: true });
  await modal.locator('input[type=number]').fill('200'); await modal.locator('#receiptFileInput4').setInputFiles(png); await h.focus();
  assert.equal(await modal.locator('input[type=number]').inputValue(), '200');
  assert.equal(await modal.locator('#receiptFileInput4').evaluate(e => e.files[0].name), png.name);
  await modal.getByRole('button', { name: '保存', exact: true }).scrollIntoViewIfNeeded();
  await h.page.screenshot({ path: path.join(out, '02-手机390-备用金凭证和保存按钮.png') });
  record('390宽度备用金选图和切窗保留，保存按钮可见'); await h.context.close();
  h = await fixture('warehouse_admin', '/suppliers', 390);
  await h.page.evaluate(() => Object.defineProperty(document.querySelector('input[aria-label="耗材产品导入文件"]'), 'showPicker', { configurable: true, value() { throw new DOMException('synthetic block', 'NotAllowedError'); } }));
  await h.page.getByRole('button', { name: '多供应商耗材导入', exact: true }).click();
  await h.page.getByRole('alert').filter({ hasText: '浏览器拦截了请重试' }).waitFor();
  await h.page.evaluate(() => Object.defineProperty(document.querySelector('input[aria-label="耗材产品导入文件"]'), 'showPicker', { configurable: true, value: undefined }));
  [chooser] = await Promise.all([h.page.waitForEvent('filechooser'), h.page.getByRole('button', { name: '多供应商耗材导入', exact: true }).click()]);
  await chooser.setFiles(state.batch_file);
  modal = h.page.getByRole('dialog', { name: '产品Excel预览与确认', exact: true });
  await modal.getByRole('button', { name: '确认导入 2 条', exact: true }).waitFor(); await modal.getByRole('checkbox').check(); await h.focus();
  assert(await modal.getByRole('checkbox').isChecked());
  await modal.getByRole('button', { name: '确认导入 2 条', exact: true }).scrollIntoViewIfNeeded();
  await h.page.screenshot({ path: path.join(out, '03-手机390-多供应商预览保留.png') });
  await modal.getByRole('button', { name: '确认导入 2 条', exact: true }).click(); await modal.waitFor({ state: 'hidden' });
  record('390宽度多供应商弹框、被拦提示和兼容回退正常');
  await h.page.getByRole('button', { name: '采购单列表', exact: true }).click();
  await h.page.getByRole('row').filter({ hasText: order.order_number }).getByRole('button', { name: '明细', exact: true }).click();
  [chooser] = await Promise.all([h.page.waitForEvent('filechooser'), h.page.getByRole('button', { name: '上传回执', exact: true }).click()]);
  await chooser.setFiles(png); await h.page.getByText('回执已上传，供应商已确认', { exact: true }).waitFor();
  assert.equal(h.writes.at(-1).endpoint, '/suppliers/purchase-orders/11/receipt'); record('390宽度采购回执可选图并传到原接口');
  await h.context.close(); assert.deepEqual(errors, []); record('无浏览器运行异常', { errors: 0 }); await browser.close();
})().catch(async error => {
  console.error(error); fs.writeFileSync(path.join(out, 'browser-error.txt'), error.stack || String(error));
  if (current) { await current.screenshot({ path: path.join(out, 'failure.png') }).catch(() => {}); fs.writeFileSync(path.join(out, 'failure-body.txt'), await current.locator('body').innerText().catch(() => '')); }
  if (browser) await browser.close(); process.exitCode = 1;
});
