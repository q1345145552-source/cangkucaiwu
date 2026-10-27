"""Disposable loopback browser fixture. No startup migrations or production configuration."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import pytest
import uvicorn
from app.main import app
from app.models import User, Supplier, SupplierProduct
from app.core.security import hash_password
from app.core.menu_registry import MENU_PERMISSIONS
from tests.test_supplier_sku_round5 import fixture


async def main():
    from urllib.parse import urlparse
    assert urlparse(os.environ['INCOMING_TEST_DATABASE_URL']).hostname == '127.0.0.1'
    port = int(os.environ['SUPPLIER_USABILITY_HTTP_PORT'])
    assert port not in (18080, 18082)
    patch = pytest.MonkeyPatch()
    try:
        with tempfile.TemporaryDirectory(prefix='supplier-acceptance-http-') as temp:
            async with fixture(Path(temp), patch) as (_, factory, _, _):
                async with factory() as db:
                    for uid in (1, 3, 4, 5, 7):
                        user = await db.get(User, uid)
                        user.password_hash = hash_password('Synthetic-Only-20261028')
                        if uid in (1, 4, 5):
                            user.extra_permissions = [p.label for p in MENU_PERMISSIONS if p.selectable]
                    (await db.get(User, 3)).extra_permissions = ['耗材库存','标准SKU目录','供应商管理']
                    (await db.get(Supplier, 1)).name = '验收供应商A'
                    original = await db.get(SupplierProduct, 1)
                    original.product_name = '验收未映射产品1'
                    for n in range(2, 7):
                        db.add(SupplierProduct(supplier_id=1, product_name=f'验收未映射产品{n}', spec='待人工核实', unit_price=10 + n, unit='个', currency='THB'))
                    await db.commit()
                class LocalServer(uvicorn.Server):
                    @contextmanager
                    def capture_signals(self):
                        yield
                server = LocalServer(uvicorn.Config(app, host='127.0.0.1', port=port, lifespan='off', log_level='warning'))
                asyncio.get_running_loop().add_signal_handler(signal.SIGINT, lambda: setattr(server, 'should_exit', True))
                print(json.dumps({'ready': True, 'url': f'http://127.0.0.1:{port}', 'synthetic_only': True}), flush=True)
                await server.serve()
    finally:
        patch.undo()


if __name__ == '__main__':
    asyncio.run(main())
