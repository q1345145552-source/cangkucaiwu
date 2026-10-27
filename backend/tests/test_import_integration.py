"""Combined import boundaries: real Excel bytes and native localhost PostgreSQL."""
import asyncio
import pytest
from sqlalchemy import event, select
from app.models import SupplierProduct, ProductImportOperation
from tests.test_supplier_sku_round5 import fixture
from tests.test_supplier_product_import_fix import excel_file, upload, confirm, count
from tests.test_incoming_operations import URL

pytestmark = pytest.mark.skipif(not URL, reason='Explicit isolated localhost PostgreSQL required')


def test_product_preview_and_successful_replay_are_bound_to_operator(tmp_path, monkeypatch):
    async def run():
        async with fixture(tmp_path, monkeypatch) as (_, factory, client, _):
            file = excel_file(tmp_path, 'operator.xlsx', [['本仓供应商', '身份核对袋', None, None, 9, '个', 'THB']])
            first = await upload(client, '/suppliers/1/import/products', file)
            rejected = await upload(client, '/suppliers/1/import/products', file, uid=3, code=409, data=confirm(first, 'operator-key'))
            assert rejected['detail']['not_created'] is True and await count(factory) == 1
            own = await upload(client, '/suppliers/1/import/products', file, uid=3)
            assert own['operator_id'] == 3 and own['preview_version'] != first['preview_version']
            payload = confirm(own, 'operator-key')
            saved = await upload(client, '/suppliers/1/import/products', file, uid=3, data=payload)
            assert saved['imported'] == 1
            replay = await upload(client, '/suppliers/1/import/products', file, uid=3, data=payload)
            assert replay['replayed'] and replay['id'] == saved['id']
            wrong_user = await upload(client, '/suppliers/1/import/products', file, uid=1, code=409, data=payload)
            assert not isinstance(wrong_user['detail'], dict) or not wrong_user['detail'].get('not_created')
            assert await count(factory) == 2
    asyncio.run(run())


def test_product_changed_file_has_exact_key_noncommit_proof_and_safe_recovery(tmp_path, monkeypatch):
    async def run():
        async with fixture(tmp_path, monkeypatch) as (_, factory, client, _):
            first = excel_file(tmp_path, 'before.xlsx', [['本仓供应商', '文件甲', None, None, 9, '个', 'THB']])
            changed = excel_file(tmp_path, 'after.xlsx', [['本仓供应商', '文件乙', None, None, 8, '个', 'THB']])
            preview = await upload(client, '/suppliers/1/import/products', first)
            rejected = await upload(client, '/suppliers/1/import/products', changed, code=409, data=confirm(preview, 'same-original-key'))
            proof = rejected['detail']
            assert proof['code'] == 'product_import_preview_changed' and proof['not_created'] is True
            assert proof['request_key'] == 'same-original-key' and await count(factory) == 1
            saved = await upload(client, '/suppliers/1/import/products', changed, data=confirm(proof['preview'], proof['request_key']))
            assert saved['imported'] == 1
            conflict = await upload(client, '/suppliers/1/import/products', first, code=409, data=confirm(preview, 'same-original-key'))
            assert not isinstance(conflict['detail'], dict) or not conflict['detail'].get('not_created')
            assert await count(factory) == 2
            async with factory() as db:
                created = (await db.execute(select(SupplierProduct).where(SupplierProduct.id != 1))).scalar_one()
                assert created.product_name == '文件乙' and created.unit_price == 8
    asyncio.run(run())


def test_product_post_insert_failure_and_six_original_retries_are_atomic(tmp_path, monkeypatch):
    async def run():
        async with fixture(tmp_path, monkeypatch) as (engine, factory, client, _):
            file = excel_file(tmp_path, 'atomic.xlsx', [['本仓供应商', '事务袋', None, None, 9, '个', 'THB']])
            pre = await upload(client, '/suppliers/1/import/products', file)
            payload = confirm(pre, 'post-insert-original-key')
            executed = []
            def fail(conn, cursor, statement, *args):
                if statement.lstrip().upper().startswith('INSERT INTO SUPPLIER_PRODUCTS'):
                    executed.append(statement)
                    raise RuntimeError('isolated product failure after INSERT')
            event.listen(engine.sync_engine, 'after_cursor_execute', fail)
            try:
                with pytest.raises(RuntimeError, match='failure after INSERT'):
                    await upload(client, '/suppliers/1/import/products', file, data=payload)
            finally:
                event.remove(engine.sync_engine, 'after_cursor_execute', fail)
            assert executed and await count(factory) == 1
            async with factory() as db:
                assert not (await db.execute(select(ProductImportOperation))).scalars().all()
            responses = await asyncio.gather(*(upload(client, '/suppliers/1/import/products', file, data=payload) for _ in range(6)))
            assert len({r['id'] for r in responses}) == 1 and sum(not r.get('replayed', False) for r in responses) == 1
            assert await count(factory) == 2
    asyncio.run(run())
