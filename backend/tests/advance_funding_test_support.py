"""历史预支回归改用本轮必填资金来源；只调整隔离测试的付款资金。"""
from contextlib import asynccontextmanager
from app.models import PaymentAccount
from tests.test_round3_permissions import hr_environment as original_hr_environment


@asynccontextmanager
async def funded_hr_environment(tmp_path, monkeypatch):
    async with original_hr_environment(tmp_path, monkeypatch) as (engine, factory, client):
        async with factory() as db:
            (await db.get(PaymentAccount, 1)).opening_balance = 1000000
            await db.commit()
        yield engine, factory, client


def funding_body(base, extra):
    body = {**base, **extra}
    if extra.get('source') == 'fund':
        body.update(funding_source='expense_fund', payment_account_id=None)
    elif extra.get('source') == 'invalid':
        body['funding_source'] = 'invalid'
    return body
