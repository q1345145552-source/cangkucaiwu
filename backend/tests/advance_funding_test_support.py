"""历史预支回归改用本轮必填资金来源；只调整隔离测试的付款资金。"""
from contextlib import asynccontextmanager
from app.models import PaymentAccount, User, UserWarehouse
from tests.round3_flow_support import grants
from tests.test_round2_permissions import set_perms
from tests.test_round3_permissions import hr_environment as original_hr_environment


@asynccontextmanager
async def funded_hr_environment(tmp_path, monkeypatch):
    async with original_hr_environment(tmp_path, monkeypatch) as (engine, factory, client):
        async with factory() as db:
            (await db.get(PaymentAccount, 1)).opening_balance = 1000000
            db.add(User(id=126,display_name="SYN independent recorder 126",username='synthetic_independent_advance_recorder',role='staff',warehouse_id=1,password_hash='synthetic',extra_permissions=['@wf-actions:1','employee_advances:operate']))
            await db.flush()
            db.add(UserWarehouse(user_id=126,warehouse_id=1))
            await db.commit()
        await grants(factory)
        await set_perms(factory,4,["员工预支"])
        client.synthetic_factory = factory
        yield engine, factory, client


def funding_body(base, extra):
    body = {**base, **extra}
    if extra.get('source') == 'fund':
        body.update(funding_source='expense_fund', payment_account_id=None)
    elif extra.get('source') == 'invalid':
        body['funding_source'] = 'invalid'
    return body
