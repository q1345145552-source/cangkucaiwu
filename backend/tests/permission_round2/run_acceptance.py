"""Round-two target acceptance, real app/JWT/PostgreSQL and synthetic data only."""
from fixtures import *
from app.models.expense_fund import FundRechargeRequest, ExpenseFundDisbursement
from app.models.data_change_history import DataChangeHistory

LOG=[]; FAIL=[]
async def main():
    engine=create_async_engine(URL)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    database._engine=engine;database._session_maker=factory
    async with engine.begin() as c:
        await c.execute(text("DROP SCHEMA public CASCADE"))
        await c.execute(text("CREATE SCHEMA public"))
        await c.run_sync(database.Base.metadata.create_all)
    async with factory() as db:
        await seed(db)
        for fid,uid in [(2,2),(4,4),(8,8)]:
            db.add(ExpenseFund(id=fid,warehouse_id=2 if uid==8 else 1,employee_id=uid,receive_date=datetime(2026,10,1),amount=500,purpose='SYNTHETIC',remaining_balance=500,fund_limit=5000,currency='THB',status='active'))
        await db.commit()
    receipt=Path(os.environ['UPLOAD_DIR'])/'fund_receipts/1/2/a.png';receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_bytes(PNG)
    async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://round2.local') as client:
        async def call(case,uid,method,path,body=None,expected=200,headers=None,check=None):
            before=await snapshot(factory)
            h={'Authorization':'Bearer '+create_access_token({'sub':str(uid)}),**(headers or {})}
            response=await client.request(method,'/api/v1'+path,json=body,headers=h)
            try: result=response.json()
            except Exception:result={'text':response.text[:2000]}
            after=await snapshot(factory)
            diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]}
            errors=[]
            if response.status_code!=expected:errors.append(f'status expected {expected}, got {response.status_code}')
            business={t:v for t,v in diff.items() if t not in ('audit_logs','data_change_history')}
            if response.status_code>=400 and business:errors.append('denial changed business tables: '+str(list(business)))
            if check:
                try:check(before,after,result)
                except Exception as exc:errors.append('database assertion: '+repr(exc))
            row={'id':case,'uid':uid,'role':ROLES[uid][0],'method':method,'path':path,'request':body,'warehouse_header':h.get('X-Warehouse-ID'),'expected_status':expected,'actual_status':response.status_code,'response':result,'database_diff':diff,'errors':errors}
            LOG.append(row);FAIL.extend(case+': '+e for e in errors)
            print(case,response.status_code,'PASS' if not errors else errors,flush=True)
            (OUT/'target-requests.json').write_text(json.dumps(LOG,ensure_ascii=False,indent=2))
            return result
        account={'account_name':'SYNTHETIC CONFIG','account_type':'cash','account_number':'-','currency':'THB','opening_balance':77,'status':'inactive'}
        newuser={'username':'round2-new','password':'synthetic-only-password','display_name':'SYNTHETIC','role':'staff','warehouse_ids':[1]}
        for uid in (2,3,4,5,6,7):
            expected=401 if uid==7 else 403
            await call(f'A-create-{uid}',uid,'POST','/users',newuser,expected)
            await call(f'A-update-{uid}',uid,'PUT','/users/5',{'is_active':False,'extra_permissions':ALL},expected)
            await call(f'A-delete-{uid}',uid,'DELETE','/users/5',expected=expected)
            await call(f'B-create-{uid}',uid,'POST','/accounts',account,expected)
            await call(f'B-update-{uid}',uid,'PUT','/accounts/1',account,expected)
            await call(f'B-toggle-{uid}',uid,'PUT','/accounts/1/toggle-status',expected=expected)
            await call(f'B-delete-{uid}',uid,'DELETE','/accounts/1',expected=expected)
        await call('A-admin-create',1,'POST','/users',newuser)
        await call('A-admin-foreign',1,'PUT','/users/8',{'is_active':False},403)
        await call('A-forged-header',1,'PUT','/users/5',{'is_active':False},403,{'X-Warehouse-ID':'2'})
        for uid in (2,3):
            for field,value in [('user_id',3),('employee_no','hijack'),('password','new-password')]:
                await call(f'A-employee-{uid}-{field}',uid,'PUT','/employees/1',{field:value},403)
            await call(f'A-bind-{uid}',uid,'POST','/employees/bind-existing-accounts',{},403)
        def login_unchanged(before,after,result):
            assert before['users']==after['users']
        await call('A-supervisor-resign-business-only',2,'POST','/employees/1/resign',{'reason':'voluntary','resignation_date':'2026-10-15'},check=login_unchanged)
        await call('A-finance-delete-business-only',3,'DELETE','/employees/1',check=login_unchanged)
        created=await call('B-admin-create',1,'POST','/accounts',{**account,'status':'active'})
        aid=created.get('id',9999)
        await call('B-admin-update-without-header',1,'PUT',f'/accounts/{aid}',account)
        await call('B-admin-extra-field',1,'PUT',f'/accounts/{aid}',{**account,'warehouse_id':2},422)
        await call('B-admin-cross',1,'PUT','/accounts/2',account,403)
        await call('B-admin-forged-header',1,'PUT',f'/accounts/{aid}',account,403,{'X-Warehouse-ID':'2'})
        await call('B-admin-toggle',1,'PUT',f'/accounts/{aid}/toggle-status')
        await call('B-finance-select',3,'GET','/accounts')
        await call('B-admin-delete-unused',1,'DELETE',f'/accounts/{aid}')
        for uid in (2,3,4):
            await call(f'C-open-{uid}',uid,'POST','/expense-fund/accounts',{'employee_id':5},403)
            await call(f'C-direct-topup-{uid}',uid,'POST','/expense-fund/accounts/1/topup',{'amount':10,'payment_account_id':1},403)
            await call(f'C-batch-approve-{uid}',uid,'POST','/expense-fund/review/batch',{'item_ids':[1],'action':'approve'},403)
            await call(f'D-fund-settings-{uid}',uid,'POST','/expense-fund/settings',{'key':'fund_limit','value':'6000'},403)
            await call(f'D-ot-{uid}',uid,'PUT','/overtime/limit',{'max_hours':60},403)
        for key in ('unknown','purchase_approval_threshold','overtime_monthly_limit','purchase_duty_separation_v1'):
            await call('D-admin-forbidden-'+key,1,'POST','/expense-fund/settings',{'key':key,'value':'0'},403)
        await call('D-admin-fund-valid',1,'POST','/expense-fund/settings',{'key':'fund_alert_threshold','value':'600'})
        await call('D-admin-fund-nan',1,'POST','/expense-fund/settings',{'key':'fund_limit','value':'NaN'},400)
        expense={'expense_date':'2026-10-20','category':'耗材','amount':10,'description':'SYNTHETIC OWN','receipt':'/uploads/fund_receipts/1/2/a.png','request_key':'round2-own-expense','currency':'THB'}
        item=await call('C-supervisor-own-expense',2,'POST','/expense-fund/accounts/2/items',expense)
        await call('C-supervisor-other-expense',2,'POST','/expense-fund/accounts/1/items',expense,403)
        iid=item.get('id',9999)
        await call('C-approve-before-verify',1,'POST','/expense-fund/review/batch',{'item_ids':[iid],'action':'approve'},409)
        def expense_no_funds(before,after,result):
            for table in ('expense_funds','expense_records','expense_fund_disbursements','reimbursement_payments'):
                assert before[table]==after[table],table
        await call('C-finance-verify-expense',3,'POST','/expense-fund/review/batch',{'item_ids':[iid],'action':'verify'},check=expense_no_funds)
        await call('C-edit-verified-expense-resets',1,'PUT',f'/expense-fund/accounts/2/items/{iid}',{'description':'SYNTHETIC corrected'},check=expense_no_funds)
        await call('C-stale-verification-rejected',1,'POST','/expense-fund/review/batch',{'item_ids':[iid],'action':'approve'},409)
        await call('C-finance-reverify-expense',3,'POST','/expense-fund/review/batch',{'item_ids':[iid],'action':'verify'},check=expense_no_funds)
        await call('C-admin-approve-expense' ,1,'POST','/expense-fund/review/batch',{'item_ids':[iid],'action':'approve'})
        rr=await call('C-supervisor-request',2,'POST','/expense-fund/recharge/request',{'amount':100,'reason':'SYNTHETIC'})
        rid=rr.get('id',9999)
        review={'request_id':rid,'action':'approve','payment_account_id':1}
        await call('C-supervisor-approve',2,'POST','/expense-fund/recharge/review',review,403)
        await call('C-finance-approve',3,'POST','/expense-fund/recharge/review',review,403)
        await call('C-execute-unapproved',3,'POST','/expense-fund/recharge/execute',review,409)
        def no_money(before,after,result):
            for table in ('expense_funds','expense_records','expense_fund_disbursements','reimbursement_payments'):
                assert before[table]==after[table], table
        await call('C-finance-verify',3,'POST','/expense-fund/recharge/review',{**review,'action':'verify'},check=no_money)
        await call('C-admin-approve',1,'POST','/expense-fund/recharge/review',review,check=no_money)
        await call('C-supervisor-execute',2,'POST','/expense-fund/recharge/execute',review,403)
        await call('C-cross-account-execute',3,'POST','/expense-fund/recharge/execute',{**review,'payment_account_id':2},400)
        def one_money(before,after,result):
            assert len(after['expense_fund_disbursements'])==len(before['expense_fund_disbursements'])+1
            assert len(after['expense_records'])==len(before['expense_records'])+1
            old=next(f for f in before['expense_funds'] if f['id']==2);new=next(f for f in after['expense_funds'] if f['id']==2)
            assert new['remaining_balance']==old['remaining_balance']+100
        await call('C-finance-execute',3,'POST','/expense-fund/recharge/execute',review,check=one_money)
        await call('C-execute-retry',4,'POST','/expense-fund/recharge/execute',review,409)
        await call('B-delete-account-with-flow',1,'DELETE','/accounts/1',expected=400)
        rr=await call('C-finance-own-request',3,'POST','/expense-fund/recharge/request',{'amount':50,'reason':'SYNTHETIC FINANCE'})
        review={'request_id':rr.get('id',9999),'action':'approve','payment_account_id':1}
        await call('C-finance-own-verify',3,'POST','/expense-fund/recharge/review',{**review,'action':'verify'},403)
        await call('C-finance-B-verify',4,'POST','/expense-fund/recharge/review',{**review,'action':'verify'})
        await call('C-finance-own-approve',3,'POST','/expense-fund/recharge/review',review,403)
        await call('C-admin-approve-finance',1,'POST','/expense-fund/recharge/review',review)
        await call('C-finance-own-pay',3,'POST','/expense-fund/recharge/execute',review,403)
        await call('C-admin-pay-finance',1,'POST','/expense-fund/recharge/execute',review)
        # On-behalf and legacy records are synthetic DB fixtures, never invented approvals.
        async with factory() as db:
            db.add_all([FundRechargeRequest(id=80,fund_id=1,warehouse_id=1,applicant_id=2,amount=10,status='pending',reason='on behalf finance'),FundRechargeRequest(id=81,fund_id=2,warehouse_id=1,applicant_id=2,amount=10,status='approved',reason='legacy no evidence'),FundRechargeRequest(id=82,fund_id=8,warehouse_id=2,applicant_id=8,amount=10,status='pending',reason='foreign')]);await db.commit()
        await call('C-on-behalf-own-verify',3,'POST','/expense-fund/recharge/review',{'request_id':80,'action':'verify'},403)
        await call('C-legacy-approved-not-executable',3,'POST','/expense-fund/recharge/execute',{'request_id':81,'action':'execute','payment_account_id':1},409)
        await call('C-foreign-request',1,'POST','/expense-fund/recharge/review',{'request_id':82,'action':'verify'},403)
        # Parent/child batch atomicity and valid path.
        for label,items in [('foreign',[{'item_id':8,'status':'approved'}]),('same-warehouse-other-parent',[{'item_id':2,'status':'approved'}]),('mixed',[{'item_id':1,'status':'approved'},{'item_id':8,'status':'approved'}]),('duplicate',[{'item_id':1,'status':'approved'},{'item_id':1,'status':'rejected'}]),('missing',[{'item_id':999,'status':'approved'}]),('invalid-state',[{'item_id':1,'status':'paid'}])]:
            await call('E-'+label,1,'POST','/reimbursement/1/review',{'items':items},400)
        # Round three requires independent verification before ordinary reimbursement approval.
        await call('E-valid-independent-verification',4,'POST','/reimbursement/1/verify')
        await call('E-valid',1,'POST','/reimbursement/1/review',{'items':[{'item_id':1,'status':'approved'}]},check=lambda b,a,r: (r['approved_amount']==100) or (_ for _ in ()).throw(AssertionError('amount')))
        await call('E-reversal-still-disabled',1,'POST','/reimbursement/1/revoke-payment',{'reason':'SYNTHETIC'},400)
        # Concurrent execution: aggregate before/after; no per-request diff attribution while overlapping.
        rr=await call('C-concurrent-request',2,'POST','/expense-fund/recharge/request',{'amount':20})
        review={'request_id':rr.get('id',9999),'action':'approve','payment_account_id':1}
        await call('C-concurrent-verify',3,'POST','/expense-fund/recharge/review',{**review,'action':'verify'})
        await call('C-concurrent-approve',1,'POST','/expense-fund/recharge/review',review)
        before=await snapshot(factory)
        responses=await asyncio.gather(*[client.post('/api/v1/expense-fund/recharge/execute',json=review,headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)})}) for uid in (3,4)])
        after=await snapshot(factory);codes=sorted(r.status_code for r in responses)
        ok=codes==[200,409] and len(after['expense_fund_disbursements'])==len(before['expense_fund_disbursements'])+1 and len(after['expense_records'])==len(before['expense_records'])+1
        LOG.append({'id':'C-concurrent-execute','expected_status':[200,409],'actual_status':codes,'response':[r.json() for r in responses],'database_diff':{t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]},'passed':ok})
        if not ok:FAIL.append('C-concurrent-execute')
        print('C-concurrent-execute',codes,ok,flush=True)
        # Independent identity aliases, delegated entries and missing approval evidence.
        from app.core.security import hash_password
        from app.models.user_warehouse import UserWarehouse
        async with factory() as db:
            db.add(User(id=90,username='synthetic-alias',display_name='SYNTHETIC ALIAS',role='staff',warehouse_id=1,password_hash=hash_password('synthetic-old-password'),extra_permissions=ALL,attendance_employee_id=3))
            await db.flush()
            db.add(UserWarehouse(user_id=90,warehouse_id=1))
            db.add(ExpenseFund(id=90,warehouse_id=1,employee_id=90,receive_date=datetime(2026,10,1),amount=100,purpose='SYNTHETIC ALIAS',remaining_balance=100,fund_limit=5000,status='active'))
            await db.flush()
            db.add(FundRechargeRequest(id=90,fund_id=90,warehouse_id=1,applicant_id=2,amount=10,status='pending',reason='delegated linked employee'))
            (await db.get(User,3)).password_hash=hash_password('synthetic-old-password')
            await db.commit()
        await call('C-linked-employee-self-verify',3,'POST','/expense-fund/recharge/review',{'request_id':90,'action':'verify'},403)
        await call('C-linked-employee-self-execute',3,'POST','/expense-fund/recharge/execute',{'request_id':90,'action':'execute','payment_account_id':1},403)
        await call('C-on-behalf-independent-verify',4,'POST','/expense-fund/recharge/review',{'request_id':80,'action':'verify'})
        await call('C-on-behalf-independent-approve',1,'POST','/expense-fund/recharge/review',{'request_id':80,'action':'approve'})
        await call('C-on-behalf-self-pay',3,'POST','/expense-fund/recharge/execute',{'request_id':80,'action':'execute','payment_account_id':1},403)
        await call('C-on-behalf-independent-pay',4,'POST','/expense-fund/recharge/execute',{'request_id':80,'action':'execute','payment_account_id':1})
        await call('A-finance-own-password',3,'POST','/auth/change-password',{'old_password':'synthetic-old-password','new_password':'synthetic-new-password'})
        await call('A-admin-update-local',1,'PUT','/users/5',{'is_active':False})
        await call('A-admin-enable-local',1,'PUT','/users/5',{'is_active':True})
        await call('A-admin-delete-new',1,'DELETE','/users/9')
        # Accepted/no-header audit must identify the authorized object warehouse, never NULL.
        async with factory() as db:
            db.add(Warehouse(id=3,name='SYNTHETIC authorized secondary',code='R2THIRD'))
            await db.flush();db.add(UserWarehouse(user_id=1,warehouse_id=3))
            db.add(PaymentAccount(id=30,warehouse_id=3,account_name='SYNTHETIC THIRD',account_type='cash',account_number='synthetic-sensitive',opening_balance=0,currency='THB'))
            await db.commit()
        def audit_scope(before,after,result):
            history=[r for r in after['data_change_history'] if r['record_id']==30 and r['module']=='accounts']
            assert history[-1]['warehouse_id']==3 and history[-1]['operator_id']==1
            assert 'synthetic-sensitive' not in json.dumps(history)
            audit=[r for r in after['audit_logs'] if r['target_id']==30 and r['module']=='accounts']
            assert audit[-1]['warehouse_id']==3
        await call('B-authorized-secondary-no-header-audit',1,'PUT','/accounts/30',account,check=audit_scope)
        async with factory() as db:
            db.add(ExpenseFund(id=30,warehouse_id=3,employee_id=1,receive_date=datetime(2026,10,1),amount=100,purpose='SYNTHETIC SCOPE',remaining_balance=100,status='active'))
            await db.flush();db.add(ExpenseFundItem(id=30,fund_id=30,expense_date=datetime(2026,10,20),category='其他',amount=10,description='SYNTHETIC SCOPE',review_status='pending'));await db.commit()
        await call('C-void-selected-warehouse-mismatch',1,'DELETE','/expense-fund/accounts/30/items/30',{'reason':'SYNTHETIC scope'},404,{'X-Warehouse-ID':'1'})
        await call('B-selected-warehouse-mismatch' ,1,'PUT','/accounts/30',account,403,{'X-Warehouse-ID':'1'})
        await call('B-supervisor-transfer-denied',2,'POST','/accounts/transfers',{'from_account_id':1,'to_account_id':30,'amount':1,'transfer_date':'2026-10-20','request_key':'SYNTHETIC'},403)
        # A failure after ledger insertion rolls back all writes and preserves approved state for retry.
        rr=await call('C-rollback-request',2,'POST','/expense-fund/recharge/request',{'amount':15})
        payload={'request_id':rr['id'],'action':'approve','payment_account_id':1}
        await call('C-rollback-verify',3,'POST','/expense-fund/recharge/review',{**payload,'action':'verify'})
        await call('C-rollback-approve',1,'POST','/expense-fund/recharge/review',payload)
        from app.services import fund_disbursement
        original_history=fund_disbursement.record_history
        async def failed_history(db,**kwargs):
            await db.flush()
            from fastapi import HTTPException
            raise HTTPException(500,'SYNTHETIC injected audit persistence failure')
        fund_disbursement.record_history=failed_history
        try:await call('C-execution-transaction-rollback',3,'POST','/expense-fund/recharge/execute',payload,500)
        finally:fund_disbursement.record_history=original_history
        await call('C-retry-after-rollback',4,'POST','/expense-fund/recharge/execute',payload)
        # Linked reimbursement rejection is atomic even when one requested item belongs elsewhere.
        async with factory() as db:
            db.add(ExpenseFundItem(id=100,fund_id=2,expense_date=datetime(2026,10,20),category='报销',amount=40,currency='THB',description='SYNTHETIC LINKED',review_status='pending'))
            await db.flush()
            db.add(Reimbursement(id=100,employee_id=2,warehouse_id=1,submit_date=datetime(2026,10,20),total_amount=40,status='fund_linked',currency='THB',is_fund_linked='1',fund_item_id=100))
            await db.flush();db.add(ReimbursementItem(id=100,reimbursement_id=100,category='其他',amount=40,review_status='pending'))
            fund=await db.get(ExpenseFund,2);fund.remaining_balance-=40
            await db.commit()
        await call('E-linked-mixed-reject-atomic',1,'POST','/reimbursement/100/review',{'items':[{'item_id':100,'status':'rejected'},{'item_id':8,'status':'rejected'}]},400)
        await call('C-linked-finance-verify',3,'POST','/expense-fund/review/batch',{'item_ids':[100],'action':'verify'})
        await call('E-linked-valid-admin-approve',1,'POST','/reimbursement/100/review',{'items':[{'item_id':100,'status':'approved'}]},check=no_money)
        def capability(expected):
            def check(before,after,result):assert result['can_fund_pay'] is expected
            return check
        for uid,allowed in ((1,False),(2,False),(3,True)):
            await call(f'C-linked-payment-capability-{uid}',uid,'GET','/reimbursement/100',check=capability(allowed))
        await call('C-linked-supervisor-payment',2,'POST','/reimbursement/100/pay',{},403)
        await call('C-linked-forged-header',3,'POST','/reimbursement/100/pay',{},403,{'X-Warehouse-ID':'2'})
        await call('C-linked-independent-payment',3,'POST','/reimbursement/100/pay',{})
        await call('C-linked-repeat-payment',4,'POST','/reimbursement/100/pay',{},400)
        # Legacy pending remains pending until an explicit new verification/approval; legacy paid never re-executes.
        async with factory() as db:
            paid=(await db.execute(select(FundRechargeRequest).where(FundRechargeRequest.status=='executed').order_by(FundRechargeRequest.id))).scalars().first()
            paid.status='approved';legacy_paid_id=paid.id
            db.add(FundRechargeRequest(id=95,fund_id=2,warehouse_id=1,applicant_id=2,amount=3,status='approved_ready',reviewer_id=1,reason='no matching evidence'))
            await db.commit()
        await call('C-legacy-paid-no-reexecution',4,'POST','/expense-fund/recharge/execute',{'request_id':legacy_paid_id,'action':'execute','payment_account_id':1},409)
        await call('C-state-only-no-approval-proof',4,'POST','/expense-fund/recharge/execute',{'request_id':95,'action':'execute','payment_account_id':1},409)
        await call('D-supervisor-price-threshold',2,'PUT','/suppliers/price-threshold',{'threshold':0},403)
        await call('D-finance-price-threshold',3,'PUT','/suppliers/price-threshold',{'threshold':0},403)
        await call('C-finance-queue',3,'GET','/expense-fund/recharge/requests')
        await call('C-finance-no-menu',6,'POST','/expense-fund/recharge/review',{'request_id':95,'action':'verify'},403)
        for uid in (2,3):
            await call(f'A-employee-create-{uid}',uid,'POST','/employees',{'name':'SYNTHETIC NEW','employee_no':'round2-new-employee','password':'synthetic-password'},403)
            for path in ('/suppliers/purchase-approval-threshold','/suppliers/concentration-threshold','/expense-approvals/threshold'):
                await call(f'D-special-rule-{uid}-{path}',uid,'PUT',path,{'threshold':0},403)
        schedule={'morning_start':'08:00','late_half':'08:30','late_one':'09:00','noon_break_start':'12:00','noon_break_end':'13:00','early_one':'16:00','early_half':'16:30','afternoon_end':'17:00','overtime_limit':0}
        for uid in (2,3):
            await call(f'D-bulk-rule-{uid}',uid,'PUT','/config/work-schedule',schedule,403)
        await call('D-admin-forged-header-rule',1,'PUT','/config/work-schedule',schedule,403,{'X-Warehouse-ID':'2'})
        # No extra grants finance, and a shared account with unauthorized secondary warehouse.
        async with factory() as db:
            db.add(User(id=91,username='synthetic-no-grants',display_name='SYNTHETIC NO GRANTS',role='staff',warehouse_id=1,password_hash='unused',extra_permissions=[]))
            await db.flush();db.add(UserWarehouse(user_id=91,warehouse_id=1));db.add(UserWarehouse(user_id=4,warehouse_id=2));await db.commit()
        ROLES[91]=('staff',1)
        await call('A-finance-no-grants',91,'POST','/users',newuser,403)
        await call('B-finance-no-grants',91,'PUT','/accounts/1',account,403)
        await call('C-finance-no-grants',91,'POST','/expense-fund/recharge/review',{'request_id':95,'action':'verify'},403)
        await call('A-admin-secondary-warehouse-outside-scope',1,'PUT','/users/4',{'is_active':False},403)
        # Administrator account disabling through employee deletion still requires the same target scope.
        async with factory() as db:
            db.add(User(id=92,username='synthetic-new-worker',display_name='SYNTHETIC WORKER',role='warehouse_labor',warehouse_id=1,password_hash='unused',extra_permissions=[]))
            await db.flush();db.add(UserWarehouse(user_id=92,warehouse_id=1));db.add(Employee(id=92,name='SYNTHETIC WORKER',warehouse_id=1,user_id=92));await db.commit()
        def disabled_target(b,a,r):assert next(u for u in a['users'] if u['id']==92)['is_active'] is False
        await call('A-admin-linked-login-disable',1,'DELETE','/employees/92',check=disabled_target)
    (OUT/'target-requests.json').write_text(json.dumps(LOG,ensure_ascii=False,indent=2))
    (OUT/'target-status.json').write_text(json.dumps({'purpose':'ROUND TWO TARGET ACCEPTANCE','test_records':len(LOG),'http_requests':sum(1 if 'method' in row else len(row['actual_status']) for row in LOG),'failures':FAIL},ensure_ascii=False,indent=2))
    await engine.dispose()
    if FAIL:raise AssertionError(FAIL)
if __name__=='__main__':asyncio.run(main())
