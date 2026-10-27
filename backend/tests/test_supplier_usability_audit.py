"""Local synthetic supplier audit; explicit disposable loopback PostgreSQL only."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from app.models import Supplier, SupplierProduct, User, DataChangeHistory
from app.models.supplier import SupplierCrossBorderPrice
from tests.test_supplier_sku_round5 import fixture
from tests.test_supplier_workflow_round1 import request
from tests.test_round2_permissions import auth, png


ACTUAL = {}

def evidence(key, value):
    ACTUAL[key] = value
    if os.environ.get('SUPPLIER_USABILITY_REPORT'):
        Path(os.environ['SUPPLIER_USABILITY_REPORT']).write_text(json.dumps(ACTUAL, ensure_ascii=False, default=str, indent=2))


def test_existing_counterpart_bill_difference_edit_history_and_statement(tmp_path, monkeypatch):
    async def run():
        import io
        from openpyxl import load_workbook
        from app.models import PayableBill
        import app.services.image_utils as images
        monkeypatch.setattr(images, 'save_image', lambda *a, **k: {'path': '/uploads/synthetic-only.png'})
        async with fixture(tmp_path, monkeypatch) as (_, f, c, _):
            created = await request(c, 'POST', '/payable', data={'supplier_id': 1, 'bill_number': 'SYNTH-DIFF', 'bill_date': '2026-10-01', 'due_date': '2026-12-01', 'amount': 100, 'confirmed_amount': 90, 'currency': 'THB'}, files={'file': ('synthetic.png', png(), 'image/png')})
            assert created['has_diff']
            async with f() as db:
                bill = await db.get(PayableBill, created['id'])
                assert bill.confirmed_amount == 90 and bill.diff_note == created['diff_note']
            await request(c, 'PUT', f'/payable/{created["id"]}', json={'confirmed_amount': 100, 'diff_note': '合成双方核对后同意100，保留处理依据'})
            async with f() as db:
                history = (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module == 'payable', DataChangeHistory.record_id == created['id'], DataChangeHistory.operation_type == 'edit'))).scalars().all()
                assert any(h.before_data.get('confirmed_amount') == 90 and h.after_data.get('confirmed_amount') == 100 for h in history)
            response = await c.get('/api/v1/payable/supplier-statement?supplier_id=1', headers={**auth(1), 'X-Warehouse-ID': '1'})
            assert response.status_code == 200
            values = list(load_workbook(io.BytesIO(response.content), read_only=True).active.values)
            assert any('SYNTH-DIFF' in row for row in values)
            await request(c, 'PUT', f'/payable/{created["id"]}', uid=7, warehouse='2', code=403, json={'diff_note': '不可跨仓改'})
            evidence('counterpart_manual_workflow', {'create': created, 'confirmed_after': 100, 'difference_resolution_logged': True, 'statement_rows': values, 'foreign_edit': 403})
    asyncio.run(run())


def test_existing_empty_inventory_read_does_not_initialize_or_value_stock(tmp_path, monkeypatch):
    async def run():
        from sqlalchemy import func
        from app.models import InventoryAccount, InventoryMovement, StandardSKU
        from tests.test_supplier_sku_round5 import sku
        async with fixture(tmp_path, monkeypatch) as (_, f, c, _):
            result = await request(c, 'GET', '/inventory')
            assert result['total'] == 0 and not result['data'] and result['pending_receipt_count'] == 0
            assert (await request(c, 'GET', '/inventory/catalog'))['data'] == []
            s = await sku(c)
            catalog = await request(c, 'GET', '/inventory/catalog')
            assert not catalog['data'][0]['opening_target']['opening_confirmed']
            assert (await request(c, 'GET', '/inventory'))['total'] == 0
            async with f() as db:
                assert (await db.execute(select(func.count()).select_from(InventoryAccount))).scalar_one() == 0
                assert (await db.execute(select(func.count()).select_from(InventoryMovement))).scalar_one() == 0
            assert (await request(c, 'GET', '/inventory/catalog', uid=7, warehouse='2'))['data'] == []
            await request(c, 'GET', '/inventory', uid=5, code=403)
            evidence('inventory_no_data', {'before': result, 'catalog_after_synthetic_sku': catalog, 'read_created_stock_records': 0, 'foreign_catalog': [], 'labor': 403})
    asyncio.run(run())


def test_ai_compare_refuses_mixed_currencies_before_provider_and_summary_is_scoped(tmp_path, monkeypatch):
    async def run():
        async with fixture(tmp_path, monkeypatch) as (_, f, c, _):
            denied = await request(c, 'POST', '/suppliers/ai-compare', code=400, json={'mode': 'product', 'compare_data': [{'currency': 'THB'}, {'currency': 'CNY'}]})
            summary = await request(c, 'GET', '/suppliers/procurement-summary')
            assert all(row['supplier_id'] != 2 for row in summary['supplier_ranking'])
            assert all(set(row['total_amount_by_currency']) <= {'THB', 'CNY'} for row in summary['supplier_ranking'])
            evidence('mixed_ai_and_summary', {'mixed_ai': denied, 'summary': summary})
    asyncio.run(run())


def test_legacy_product_comparison_never_ranks_different_currencies_or_warehouses(tmp_path, monkeypatch):
    async def run():
        async with fixture(tmp_path, monkeypatch) as (_, f, c, _):
            async with f() as db:
                db.add_all([
                    SupplierProduct(supplier_id=1, product_name='同名袋', spec='38cm', unit='个', unit_price=800, currency='CNY'),
                    SupplierProduct(supplier_id=3, product_name='同名袋', spec='38cm', unit='个', unit_price=50, currency='THB'),
                    SupplierProduct(supplier_id=2, product_name='同名袋', spec='38cm', unit='个', unit_price=1, currency='THB'),
                ])
                await db.commit()
            result = await request(c, 'GET', '/suppliers/compare-prices?product_name=同名袋')
            evidence('product_comparison', result)
            assert {r['supplier_id'] for r in result['data']} == {1, 3}
            assert all(r['rank_in_group'] == 1 for r in result['data'])
            thb = await request(c, 'GET', '/suppliers/compare-prices?product_name=同名袋&currency=THB')
            assert len(thb['data']) == 1 and thb['data'][0]['currency'] == 'THB'
            foreign = await request(c, 'GET', '/suppliers/compare-prices?product_name=同名袋', uid=7, warehouse='2')
            assert {r['supplier_id'] for r in foreign['data']} == {2}
            await request(c, 'GET', '/suppliers/compare-prices', uid=5, code=403)
    asyncio.run(run())


def test_logistics_retains_both_currencies_and_does_not_guess_yiwu_fx(tmp_path, monkeypatch):
    async def run():
        async with fixture(tmp_path, monkeypatch) as (_, f, c, _):
            async with f() as db:
                for currency, price in [('CNY', 800), ('CNY', 600), ('THB', 50)]:
                    db.add(SupplierCrossBorderPrice(supplier_id=1, transport_method='陆运', cargo_type='普货', origin_warehouse='深圳仓', price_per_cbm=price, currency=currency))
                db.add(SupplierCrossBorderPrice(supplier_id=2, transport_method='陆运', cargo_type='普货', origin_warehouse='深圳仓', price_per_cbm=1, currency='THB'))
                await db.commit()
            result = await request(c, 'GET', '/suppliers/compare-logistics?origin_warehouse=深圳仓')
            evidence('logistics', result)
            assert {(r['currency'], r['price_per_cbm']) for r in result['data']} == {('CNY', 800), ('CNY', 600), ('THB', 50)}
            yiwu = await request(c, 'GET', '/suppliers/compare-logistics?origin_warehouse=义乌仓')
            evidence('yiwu', yiwu)
            yuan = next(r for r in yiwu['data'] if r['currency'] == 'CNY' and r['price_per_cbm'] == 920)
            assert {r['price_per_cbm'] for r in yiwu['data'] if r['currency'] == 'CNY'} == {920, 720}
            assert len({r['price_id'] for r in result['data']}) == 3
            baht = next(r for r in yiwu['data'] if r['currency'] == 'THB')
            assert yuan['price_per_cbm'] == 920 and yuan['min_amount'] == 276
            assert baht['price_per_cbm'] is None and baht['min_amount'] is None and not baht['comparable']
            assert '待确认' in baht['price_note']
    asyncio.run(run())


async def evaluate_function(f):
    # HTTP role policy is intentionally unchanged: router rejects super-admin,
    # handler rejects other roles. Test persistence separately, not a new grant.
    from app.api.v1.suppliers import ai_evaluate
    async with f() as db:
        user = await db.get(User, 2)
        user._warehouse_ids = [1]
        result = await ai_evaluate(1, current_user=user, db=db, _perm=None)
        await db.commit()
        return result


def test_ai_unconfigured_and_failed_results_do_not_persist_as_evaluations(tmp_path, monkeypatch):
    async def run():
        import app.config as config
        async with fixture(tmp_path, monkeypatch) as (_, f, c, _):
            monkeypatch.setattr(config, 'get_settings', lambda: SimpleNamespace(DEEPSEEK_API_KEY='', DEEPSEEK_BASE_URL='http://unused.invalid'))
            await request(c, 'GET', '/suppliers/1/ai-evaluation', uid=2, code=403)
            unconfigured = await evaluate_function(f)
            async with f() as db:
                assert (await db.get(Supplier, 1)).ai_evaluation is None
            assert unconfigured['status'] == 'unavailable'
            await request(c, 'GET', '/suppliers/1/ai-evaluation', uid=1, code=403)
            await request(c, 'GET', '/suppliers/2/ai-evaluation', uid=2, code=403)
            evidence('ai_unavailable', unconfigured)
    asyncio.run(run())


def test_ai_success_keeps_timestamp_basis_history_and_never_changes_business_state(tmp_path, monkeypatch):
    async def run():
        import app.config as config
        import openai
        async with fixture(tmp_path, monkeypatch) as (_, f, c, _):
            monkeypatch.setattr(config, 'get_settings', lambda: SimpleNamespace(DEEPSEEK_API_KEY='synthetic-key-not-networked', DEEPSEEK_BASE_URL='http://unused.invalid'))
            prompts = []
            class MockClient:
                def __init__(self, **kw):
                    self.chat = SimpleNamespace(completions=self)
                    self.http = kw['http_client']
                async def create(self, **kw):
                    prompts.append(kw)
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='仅依据档案，缺少准时率和退货证据，需人工核实。'))])
                async def close(self):
                    await self.http.aclose()
                    raise RuntimeError('synthetic provider cleanup error must not discard result')
            monkeypatch.setattr(openai, 'AsyncOpenAI', MockClient)
            result = await evaluate_function(f)
            async with f() as db:
                s = await db.get(Supplier, 1)
                assert s.ai_evaluated_at is not None and s.ai_evaluation == result
                assert s.is_active == 'true'
                history = (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module == 'suppliers', DataChangeHistory.operation_type == 'ai_evaluation'))).scalars().all()
                assert len(history) == 1 and history[0].operator_id == 2 and history[0].warehouse_id == 1
            assert result['basis']['supplier_id'] == 1 and result['evaluated_by'] == 2
            assert result['evaluated_at'] and result['status'] == 'generated'
            assert '缺失' in prompts[0]['messages'][0]['content']
            class FailedClient(MockClient):
                async def create(self, **kw):
                    raise RuntimeError('synthetic provider failure')
            monkeypatch.setattr(openai, 'AsyncOpenAI', FailedClient)
            failed = await evaluate_function(f)
            assert failed['status'] == 'failed'
            async with f() as db:
                assert (await db.get(Supplier, 1)).ai_evaluation == result
            evidence('ai_success_and_failed_retry', {'success': result, 'failed_retry': failed, 'prior_success_retained': True, 'supplier_state_unchanged': True})
    asyncio.run(run())
