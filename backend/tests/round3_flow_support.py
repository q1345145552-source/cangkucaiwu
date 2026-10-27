"""Synthetic regression setup using real route/JWT approval chains, never proof fabrication."""
from sqlalchemy import select
from app.database import Base
from app.models import User
from app.models.payroll import PayrollRecord
from tests.test_round2_permissions import auth

async def grants(factory, uid=3):
    async with factory() as db:
        user=await db.get(User,uid)
        user.extra_permissions=list(dict.fromkeys([*(user.extra_permissions or []),'工资','垫款单','报销管理','备用金管理','员工预支']))
        await db.commit()

async def money_state(factory):
    # Workflow states/history are expected to change; payment, expense and fund effects must not.
    async with factory() as db:
        result={}
        for name in ('expense_records','payable_payments','reimbursement_payments','cash_advance_repayments','expense_fund_items'):
            table=Base.metadata.tables[name]
            result[name]=[tuple(r) for r in (await db.execute(select(table).order_by(table.c.id))).all()]
        table=Base.metadata.tables['expense_funds']
        result['fund_balances']=[tuple(r) for r in (await db.execute(select(table.c.id,table.c.remaining_balance).order_by(table.c.id))).all()]
        return result

async def post_ok(client,path,uid,body=None):
    response=await client.post('/api/v1'+path,headers=auth(uid),json=body)
    assert response.status_code==200,(path,uid,response.text)
    return response

async def prepare_payroll(factory,client,*ids):
    """Seed rows are draft synthetic inputs; confirmation is always a real administrator action."""
    await grants(factory)
    async with factory() as db:
        for rid in ids:
            row=await db.get(PayrollRecord,rid)
            assert not row.disbursed and not row.voided
            row.status='pending';row.confirmed_by=None;row.confirmed_at=None
        await db.commit()
    before=await money_state(factory)
    for rid in ids:await post_ok(client,f'/payroll/{rid}/confirm',1)
    assert await money_state(factory)==before,'confirmation must not pay'

async def verify_approve_cash(factory,client,aid):
    await grants(factory)
    before=await money_state(factory)
    await post_ok(client,f'/cash-advances/{aid}/verify',3)
    assert await money_state(factory)==before,'cash verification must not pay'
    response=await post_ok(client,f'/cash-advances/{aid}/confirm',1)
    assert await money_state(factory)==before,'cash approval must not pay'
    return response

async def approve_advance(factory,client,aid):
    await grants(factory)
    before=await money_state(factory)
    await post_ok(client,f'/employee-advances/{aid}/verify',3)
    assert await money_state(factory)==before,'advance verification must not pay'
    response=await post_ok(client,f'/employee-advances/{aid}/approve',1)
    assert response.json()['approval_status']=='approved_ready'
    assert await money_state(factory)==before,'advance approval must not pay'
    return response

async def execute_advance(factory,client,aid):
    await approve_advance(factory,client,aid)
    return await post_ok(client,f'/employee-advances/{aid}/execute',3)

async def assert_disabled(client,path,uid=1):
    from app.main import app
    from app.core.financial_reversals import reject_disabled_financial_reversal,REVERSAL_DISABLED_MESSAGE
    assert reject_disabled_financial_reversal not in app.dependency_overrides
    response=await client.post('/api/v1'+path,headers=auth(uid),json={'reason':'synthetic disabled check'})
    assert response.status_code==400 and response.json()=={'detail':REVERSAL_DISABLED_MESSAGE},response.text

async def historical_payroll(factory,client,rid):
    """Build an already-reversed historical fixture with SQL. Never call a reversal handler."""
    from app.models.income_expense import ExpenseRecord
    from app.services.data_history import record_history
    await assert_disabled(client,f'/payroll/{rid}/revoke-disbursement')
    async with factory() as db:
        row=await db.get(PayrollRecord,rid);expense_id=row.expense_record_id;loan_id=row.cash_advance_id
        expense=await db.get(ExpenseRecord,expense_id) if expense_id else None
        admin=await db.get(User,1)
        if expense:
            await record_history(db,module='expense',record_id=expense.id,operator=admin,operation_type='delete',before={'amount':expense.amount,'payroll_record_id':rid},after={'remark':'合成历史：因为撤销发放而冲销'},warehouse_id=row.warehouse_id)
            row.expense_record_id=None;await db.flush();await db.delete(expense)
        if loan_id:
            await record_history(db,module='cash_advances',record_id=loan_id,operator=admin,operation_type='payroll_use_revoke',after={'fixture':'pre-existing historical reversal'},warehouse_id=row.warehouse_id)
        row.payment_account_id=None;row.cash_advance_id=None;row.funding_source=None
        row.disbursed=False;row.disbursed_at=None;row.disbursed_by=None;row.status='confirmed'
        await db.commit()
    return {'fixture':'historical, not HTTP execution','reversed_expense_id':expense_id,'reversed_cash_advance_id':loan_id}

async def historical_cash(factory,client,repayment_id,reason='账户选错，合成历史'):
    from app.models import CashAdvance,CashAdvanceRepayment,PaymentAccount
    from app.core.timezone import thai_now
    from app.api.v1.cash_advance import _repayment_result
    await assert_disabled(client,f'/cash-advances/repayments/{repayment_id}/revoke')
    async with factory() as db:
        repayment=await db.get(CashAdvanceRepayment,repayment_id);loan=await db.get(CashAdvance,repayment.cash_advance_id)
        assert repayment.status=='active'
        loan.repaid_amount-=repayment.amount;loan.status='confirmed'
        repayment.status='revoked';repayment.revoked_by_id=1;repayment.revoked_by_name='synthetic historical admin'
        repayment.revoked_at=thai_now();repayment.revoke_reason=reason
        await db.flush()
        result=await _repayment_result(db,repayment,loan,await db.get(PaymentAccount,repayment.account_id))
        await db.commit()
    return result

async def historical_reimbursement(factory,client,rid,reason='付款账户选错，合成历史'):
    from app.models import PaymentAccount,ExpenseFund,ExpenseFundItem
    from app.models.reimbursement import Reimbursement
    from app.models.reimbursement_payment import ReimbursementPayment
    from app.models.income_expense import ExpenseRecord
    from app.services.reimbursement_payment import result
    from app.core.timezone import thai_now
    await assert_disabled(client,f'/reimbursement/{rid}/revoke-payment')
    async with factory() as db:
        row=await db.get(Reimbursement,rid)
        payment=(await db.execute(select(ReimbursementPayment).where(ReimbursementPayment.reimbursement_id==rid,ReimbursementPayment.status=='active'))).scalar_one()
        expense=await db.get(ExpenseRecord,row.expense_record_id) if row.expense_record_id else None
        if row.is_fund_linked=='1' and row.fund_item_id:
            item=await db.get(ExpenseFundItem,row.fund_item_id);fund=await db.get(ExpenseFund,item.fund_id)
            fund.remaining_balance+=item.amount;row.fund_item_id=None;await db.flush();await db.delete(item)
        row.expense_record_id=None
        if expense:await db.flush();await db.delete(expense)
        payment.status='revoked';payment.revoked_by_id=1;payment.revoked_by_name='synthetic historical admin';payment.revoked_at=thai_now();payment.revoke_reason=reason
        row.status=payment.previous_status;row.paid_at=None;row.payment_account_id=None;row.payment_method=None;row.payment_voucher_path=None;row.cash_advance_id=None
        row.funding_source='expense_fund' if row.is_fund_linked=='1' else None
        await db.flush();account=await db.get(PaymentAccount,payment.payment_account_id) if payment.payment_account_id else None
        data=await result(db,row,payment,account);await db.commit()
    return data

class DeferredChecks:
    """Keep monetary failures red while reaching independent later assertions.

    This is not xfail/skip: finish raises every captured AssertionError. Only explicitly
    named independent read assertions may be grouped; never wrap setup or mutations.
    """
    def __init__(self):self.failures=[]
    def check(self,label):
        from contextlib import contextmanager
        @contextmanager
        def capture():
            try:yield
            except AssertionError as exc:self.failures.append({'assertion':label,'actual_failure':str(exc)})
        return capture()
    def finish(self):
        assert not self.failures,self.failures
