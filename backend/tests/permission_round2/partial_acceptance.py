"""Real route/JWT/isolated PostgreSQL acceptance for permissions7-r02-fix01-20261028."""
from fixtures import *
from app.models.reimbursement_payment import ReimbursementPayment
from app.services import reimbursement_payment as payments
OUT=ROOT/'docs/permissions-r02-fix01-20261028'
LOG=[]; FAIL=[]

def row(s,t,i):return next(x for x in s[t] if x['id']==i)
def unchanged_money(a,b,_):
    for t in ('expense_funds','reimbursement_payments','expense_records','expense_fund_disbursements'):
        assert a[t]==b[t],t

def paid_once(rid,amount):
    def check(a,b,res):
        assert row(b,'reimbursements',rid)['status']=='paid'
        found=[p for p in b['reimbursement_payments'] if p['reimbursement_id']==rid]
        assert len(found)==1 and float(found[0]['amount'])==amount,found
        assert a['expense_funds']==b['expense_funds']
        assert a['expense_records']==b['expense_records']
        assert len(b['reimbursement_payments'])==len(a['reimbursement_payments'])+1
    return check

async def main():
    engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
    database._engine=engine;database._session_maker=factory
    async with engine.begin() as c:
        await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'))
        await c.run_sync(database.Base.metadata.create_all)
    async with factory() as db:
        await seed(db)
        for fid,uid in [(2,2),(4,4),(8,8)]:
            db.add(ExpenseFund(id=fid,warehouse_id=2 if uid==8 else 1,employee_id=uid,receive_date=datetime(2026,10,1),amount=5000,purpose='SYNTHETIC',remaining_balance=5000,fund_limit=5000,currency='THB',status='active'))
        db.add_all([User(id=90,username='synthetic-alias',display_name='SYNTHETIC alias',role='staff',warehouse_id=1,password_hash='synthetic',extra_permissions=ALL,is_active=True,attendance_employee_id=3),User(id=91,username='synthetic-no-extra',display_name='SYNTHETIC no extras',role='staff',warehouse_id=1,password_hash='synthetic',extra_permissions=[],is_active=True)])
        await db.commit()
    async def sample(rid,fid=2):
        async with factory() as db:
            f=await db.get(ExpenseFund,fid)
            db.add(ExpenseFundItem(id=rid,fund_id=fid,expense_date=datetime(2026,10,20),category='报销',amount=40,currency='THB',description='SYNTHETIC partial',review_status='pending'))
            await db.flush()
            db.add(Reimbursement(id=rid,employee_id=f.employee_id,warehouse_id=f.warehouse_id,submit_date=datetime(2026,10,20),total_amount=40,status='fund_linked',currency='THB',is_fund_linked='1',fund_item_id=rid));await db.flush()
            db.add_all([ReimbursementItem(id=rid*10,reimbursement_id=rid,category='其他',amount=30,review_status='pending'),ReimbursementItem(id=rid*10+1,reimbursement_id=rid,category='其他',amount=10,review_status='pending')])
            f.remaining_balance-=40;await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://fix01.local') as client:
        async def call(name,uid,path,body=None,status=200,check=None,method='POST',headers=None):
            before=await snapshot(factory)
            response=await client.request(method,'/api/v1'+path,json=body,headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)}),**(headers or {})})
            try:result=response.json()
            except Exception:result={'text':response.text}
            after=await snapshot(factory);diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]}
            errors=[]
            if response.status_code!=status:errors.append(f'expected {status}, got {response.status_code}')
            if response.status_code>=400 and any(t not in ('audit_logs','data_change_history') for t in diff):errors.append('denial changed business tables')
            if check:
                try:check(before,after,result)
                except Exception as e:errors.append(repr(e))
            LOG.append(dict(id=name,user_id=uid,path=path,method=method,request=body,expected=status,status=response.status_code,response=result,database_diff=diff,errors=errors));FAIL.extend(name+': '+e for e in errors)
            print(name,response.status_code,errors or 'PASS',flush=True)
            return result
        async def verify(rid,uid=3):return await call(f'verify-{rid}',uid,'/expense-fund/review/batch',{'item_ids':[rid],'action':'verify'},check=unchanged_money)
        def decisions(rid,mode='partial'):
            return {'items':[{'item_id':rid*10,'status':'rejected' if mode=='reject' else 'approved'},{'item_id':rid*10+1,'status':'approved' if mode=='full' else 'rejected'}]}
        async def approve(rid,mode='partial'):
            def check(a,b,result):
                unchanged_money(a,b,result)
                expected=40 if mode=='full' else 30
                assert result['approved_amount']==expected
                parent=row(b,'reimbursements',rid)
                assert parent['total_amount']==expected
                assert parent['status']==('approved' if mode=='full' else 'partially_approved')
                item=row(b,'expense_fund_items',rid)
                assert item['review_status']=='approved' and item['amount']==40
                proofs=[x for x in b['data_change_history'] if x['module']=='fund_authorization' and x['record_id']==rid and x['operation_type']=='item_approve']
                assert len(proofs)==1
                snapshot=proofs[0]['after_data']['reimbursement']
                assert float(snapshot['total_amount'])==expected and len(snapshot['items'])==2
                assert sum(float(x['amount']) for x in snapshot['items'] if x['status']=='approved')==expected
            return await call(f'approve-{rid}-{mode}',1,f'/reimbursement/{rid}/review',decisions(rid,mode),check=check if mode!='reject' else None)
        for rid,mode in [(200,'partial'),(201,'full')]:
            await sample(rid);await verify(rid)
            # Round-three shared capabilities must preserve the round-two approval page.
            def approve_capability(a,b,result):assert result['capabilities']['can_approve'] is True
            await call(f'approval-capability-{rid}',1,f'/reimbursement/{rid}',method='GET',check=approve_capability)
            await approve(rid,mode)
            def capability(a,b,r):assert r['can_fund_pay'] is True
            await call(f'capability-{rid}',3,f'/reimbursement/{rid}',method='GET',check=capability)
            await call(f'cannot-reapprove-{rid}',1,f'/reimbursement/{rid}/review',decisions(rid,'full'),409 if mode=='partial' else 400)
            for action in ('approve','reject','verify'):
                await call(f'cross-entry-{rid}-{action}',1,'/expense-fund/review/batch',{'item_ids':[rid],'action':action},409)
            await call(f'pay-{rid}',3,f'/reimbursement/{rid}/pay',{},check=paid_once(rid,30 if mode=='partial' else 40))
            await call(f'repeat-pay-{rid}',4,f'/reimbursement/{rid}/pay',{},400)
        await sample(202);await verify(202)
        def refunded(a,b,r):
            assert row(b,'expense_funds',2)['remaining_balance']-row(a,'expense_funds',2)['remaining_balance']==40
            assert a['reimbursement_payments']==b['reimbursement_payments']
        await call('reject-all',1,'/reimbursement/202/review',decisions(202,'reject'),check=refunded)
        await call('reject-all-repeat',1,'/reimbursement/202/review',decisions(202,'reject'),400)
        await call('reject-all-batch-repeat',1,'/expense-fund/review/batch',{'item_ids':[202],'action':'reject'},409)
        await call('reject-all-pay',3,'/reimbursement/202/pay',{},400)
        await sample(203);await verify(203)
        await call('missing-line-decision',1,'/reimbursement/203/review',{'items':decisions(203)['items'][:1]},400)
        await approve(203)
        # Concurrent real requests, parent lock guarantees one active payment.
        before=await snapshot(factory)
        async def send(uid):
            r=await client.post('/api/v1/reimbursement/203/pay',json={},headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)})});return {'status':r.status_code,'response':r.json()}
        results=await asyncio.gather(send(3),send(4));after=await snapshot(factory);errors=[]
        try:
            assert sorted(x['status'] for x in results)==[200,400]
            paid_once(203,30)(before,after,None)
        except Exception as e:errors.append(repr(e))
        LOG.append(dict(id='concurrent-payment',expected=[200,400],results=results,database_diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]},errors=errors));FAIL.extend(errors)
        print('concurrent-payment',results,errors or 'PASS',flush=True)
        await sample(204);await verify(204);await approve(204)
        original=payments.record_history
        async def fail_after_payment(*args,**kwargs):raise RuntimeError('SYNTHETIC failure after payment flush')
        payments.record_history=fail_after_payment
        try:await call('payment-mid-transaction-failure',3,'/reimbursement/204/pay',{},500)
        finally:payments.record_history=original
        await call('payment-after-rollback',4,'/reimbursement/204/pay',{},check=paid_once(204,30))
        # Batch approval must explicitly approve all untouched details and bind them in proof.
        await sample(205);await verify(205)
        await call('batch-full-approve',1,'/expense-fund/review/batch',{'item_ids':[205],'action':'approve'},check=unchanged_money)
        await call('batch-full-pay',3,'/reimbursement/205/pay',{},check=paid_once(205,40))
        # Stale approval evidence cannot authorize changed amounts or decisions.
        for rid,mutation in [(206,'amount'),(207,'status'),(208,'description')]:
            await sample(rid);await verify(rid);await approve(rid)
            async with factory() as db:
                d=await db.get(ReimbursementItem,rid*10)
                if mutation=='amount':d.amount=29
                elif mutation=='status':d.review_status='pending'
                else:d.description='SYNTHETIC changed after approval'
                await db.commit()
            await call(f'stale-{mutation}',3,f'/reimbursement/{rid}/pay',{},409)
        await sample(209,1) # Admin recorded on behalf of finance A; beneficiary is finance A.
        await call('on-behalf-self-verify',3,'/expense-fund/review/batch',{'item_ids':[209],'action':'verify'},403)
        await verify(209,4)
        await call('on-behalf-self-approve',3,'/reimbursement/209/review',decisions(209),403)
        await approve(209)
        await call('on-behalf-self-pay',3,'/reimbursement/209/pay',{},403)
        await call('employee-alias-self-pay',90,'/reimbursement/209/pay',{},403)
        await call('independent-finance-pay',4,'/reimbursement/209/pay',{},check=paid_once(209,30))
        await sample(210);await verify(210);await approve(210)
        for uid in (2,5,6,7,8,91):
            await call(f'pay-role-{uid}',uid,'/reimbursement/210/pay',{},401 if uid==7 else 403)
        await call('pay-forged-warehouse',3,'/reimbursement/210/pay',{},403,headers={'X-Warehouse-ID':'2'})
        await sample(211,8)
        await call('foreign-review',1,'/reimbursement/211/review',decisions(211),403)
        await call('foreign-batch',1,'/expense-fund/review/batch',{'item_ids':[211],'action':'verify'},403)
        # Valid + invalid review remains atomic.
        await sample(212);await verify(212)
        await call('mixed-parent-review',1,'/reimbursement/212/review',{'items':[decisions(212)['items'][0],decisions(211)['items'][1]]},400)
        await sample(213);await verify(213)
        async with factory() as db:
            (await db.get(ReimbursementItem,2130)).description='SYNTHETIC changed after verification';await db.commit()
        await call('stale-verification',1,'/reimbursement/213/review',decisions(213),409)
        await call('stale-verification-batch',1,'/expense-fund/review/batch',{'item_ids':[213],'action':'approve'},409)
        await sample(214);await verify(214)
        await call('missing-line-only-reject',1,'/reimbursement/214/review',{'items':[decisions(214,'reject')['items'][0]]},400)
        await call('batch-reject-all',1,'/expense-fund/review/batch',{'item_ids':[214],'action':'reject'},check=refunded)
        await call('batch-reject-repeat',1,'/expense-fund/review/batch',{'item_ids':[214],'action':'reject'},409)
        await call('batch-reject-pay',3,'/reimbursement/214/pay',{},400)
        await sample(215);await verify(215);await approve(215)
        from app.models.data_change_history import DataChangeHistory
        async with factory() as db:
            evidence=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='fund_authorization',DataChangeHistory.record_id==215,DataChangeHistory.operation_type=='item_approve'))).scalar_one()
            evidence.after_data={k:v for k,v in evidence.after_data.items() if k!='reimbursement'}
            await db.commit()
        await call('legacy-item-only-proof',3,'/reimbursement/215/pay',{},409)
        # Real creation exercises existing floating storage and payment precision (0.1+0.2).
        for mode in ('full','partial'):
            created=await call('decimal-create-'+mode,2,'/reimbursement',{'submit_date':'2026-10-20','currency':'THB','is_fund_linked':'1','items':[{'category':'其他','amount':0.1},{'category':'其他','amount':0.2}]})
            rid=created['id']
            detail=await call('decimal-details-'+mode,3,f'/reimbursement/{rid}',method='GET')
            await call('decimal-verify-'+mode,3,'/expense-fund/review/batch',{'item_ids':[detail['fund_item_id']],'action':'verify'},check=unchanged_money)
            await call('decimal-approve-'+mode,1,f'/reimbursement/{rid}/review',{'items':[{'item_id':d['id'],'status':'approved' if mode=='full' or i==0 else 'rejected'} for i,d in enumerate(detail['items'])]},check=unchanged_money)
            await call('decimal-pay-'+mode,3,f'/reimbursement/{rid}/pay',{},check=paid_once(rid,0.3 if mode=='full' else 0.1))
    (OUT/'requests.json').write_text(json.dumps(LOG,ensure_ascii=False,indent=2))
    (OUT/'status.json').write_text(json.dumps({'marker':'permissions7-r02-fix01-20261028','records':len(LOG),'http_requests':len(LOG)+1,'failures':FAIL},ensure_ascii=False,indent=2))
    await engine.dispose()
    assert not FAIL,FAIL
if __name__=='__main__':asyncio.run(main())
