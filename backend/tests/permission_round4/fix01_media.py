"""Real uploaded receipt / JSON-media regression; no auth substitution."""
from fixtures import *

VALID = [('standard', 'application/json'), ('charset', 'application/json; charset=utf-8'),
         ('vendor', 'application/vnd.review+json'), ('vendor-charset', 'application/vnd.review+json; charset=utf-8'),
         ('problem', 'application/problem+json'), ('mixed-case', 'Application/JSON'), ('missing', None)]
INVALID = [('plain', 'text/plain'), ('jsonp', 'application/jsonp'), ('bad-json-suffix', 'application/json-invalid'), ('empty', '')]

async def scenarios(factory, client, original_log, out):
    records, failures = [], []
    async def call(name, uid, method, path, body=None, media='application/json', expected=200, files=None, raw=None):
        before = await snapshot(factory)
        headers = {'Authorization': 'Bearer ' + create_access_token({'sub': str(uid)})}
        if media is not None: headers['Content-Type'] = media
        kwargs = {'content': raw if raw is not None else json.dumps(body).encode()} if body is not None or raw is not None else {}
        if files is not None:
            headers.pop('Content-Type', None); kwargs = {'files': files}
        response = await client.request(method, path if path.startswith('/uploads/') else '/api/v1'+path, headers=headers, **kwargs)
        after = await snapshot(factory)
        diff = {t: {'before': before[t], 'after': after[t]} for t in before if before[t] != after[t]}
        errors = []
        if response.status_code != expected: errors.append(f'expected {expected}, actual {response.status_code}')
        if response.status_code >= 400:
            if any(t not in ('audit_logs', 'data_change_history') for t in diff): errors.append('rejection changed business tables')
            if [r for r in before['data_change_history'] if r.get('module') == 'makeup_request'] != [r for r in after['data_change_history'] if r.get('module') == 'makeup_request']: errors.append('rejection changed makeup requests')
        if method in ('POST', 'PUT') and path.startswith('/reimbursement') and response.status_code == 200:
            if any(t not in ('reimbursements','reimbursement_items','data_change_history','audit_logs') for t in diff): errors.append('receipt request changed unrelated business tables')
            rid = response.json().get('id') if method == 'POST' else int(path.split('/')[2].split('?')[0])
            saved = [r for r in after['reimbursement_items'] if r['reimbursement_id'] == rid]
            if len(saved) != len(body['items']) or [x['receipt'] for x in saved] != [x.get('receipt') for x in body['items']]: errors.append('saved receipt mismatch')
            parent = next(r for r in after['reimbursements'] if r['id'] == rid)
            if parent['employee_id'] != uid or parent['warehouse_id'] != 1 or parent['status'] != 'pending' or parent['total_amount'] != sum(x['amount'] for x in body['items']): errors.append('unexpected parent identity/state/amount')
        try: result = response.json()
        except Exception: result = {'bytes': len(response.content), 'content_type': response.headers.get('content-type')}
        records.append({'id':name,'user':uid,'method':method,'path':path,'content_type':media,'request':body,'raw':raw.decode(errors='replace') if raw is not None else None,'expected':expected,'actual':response.status_code,'response':result,'database_diff':diff,'errors':errors})
        failures.extend(name+': '+e for e in errors)
        print(name, response.status_code, errors or 'PASS', flush=True)
        (out/'media-requests.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
        return result

    # Reuse the exact real uploaded fixture that independent review demonstrated.
    other_receipt = next(r['response']['receipt'] for r in original_log if r.get('id') == 'D-own-fund-upload')
    await call('FIX01-probe-other-file-unreadable',11,'GET',other_receipt,expected=403)
    async with factory() as db:
        for fid, uid, wid in ((20,2,1),(21,11,1),(22,8,2)):
            db.add(ExpenseFund(id=fid,warehouse_id=wid,employee_id=uid,receive_date=datetime(2026,10,1),amount=0,purpose='SYNTHETIC RECEIPT OWNER',remaining_balance=0,fund_limit=5000,currency='THB',status='active'))
        await db.commit()
    receipts = {3: other_receipt}
    for fid, uid in ((20,2),(21,11),(22,8)):
        r = await call(f'FIX01-upload-{uid}',uid,'POST',f'/expense-fund/accounts/{fid}/upload-receipt?view=self',files={'file':('synthetic.png',PNG,'image/png')})
        receipts[uid] = r['receipt']
        await call(f'FIX01-own-file-read-{uid}',uid,'GET',r['receipt'])
    # A true own receipt can be used for a new request and subsequent edit under every accepted media type.
    for uid in (2,3,11):
        own = {'submit_date':'2026-10-24','items':[{'category':'其他','amount':1,'receipt':receipts[uid]}]}
        parent = await call(f'FIX01-edit-parent-{uid}',uid,'POST','/reimbursement?view=self',own)
        for label, media in VALID + INVALID:
            for ownership, receipt in [('own',receipts[uid]),('same-warehouse-other',receipts[11] if uid == 3 else receipts[3]),('foreign',receipts[8])]:
                payload = {'submit_date':'2026-10-24','items':[{'category':'其他','amount':2,'receipt':receipt}]}
                expected = 415 if label == 'empty' else 422 if (label,media) in INVALID else 200 if ownership == 'own' else 403
                for method, path in [('POST','/reimbursement?view=self'),('PUT',f"/reimbursement/{parent['id']}?view=self")]:
                    await call(f'FIX01-{uid}-{method}-{label}-{ownership}',uid,method,path,payload,media,expected)
        await call(f'FIX01-own-file-still-readable-{uid}',uid,'GET',receipts[uid])
        if uid == 11:
            await call('FIX01-other-file-still-unreadable',uid,'GET',receipts[3],expected=403)
        for method, path in [('POST','/reimbursement?view=self'),('PUT',f"/reimbursement/{parent['id']}?view=self")]:
            for raw in (b'{bad json', b'[]', b'null'):
                await call(f'FIX01-malformed-{uid}-{method}-{raw!r}',uid,method,path,media='application/vnd.review+json',raw=raw,expected=422)
            mixed = {**own,'items':own['items']+[{'category':'其他','amount':9,'receipt':receipts[8]}]}
            await call(f'FIX01-mixed-atomic-{uid}-{method}',uid,method,path,mixed,'application/vnd.review+json',403)

    # The role ceiling must also see sensitive employee fields in +json and missing-header bodies.
    for uid in (2,4):
        for label,media in VALID:
            for field in ('daily_wage','bank_account_number','salary_template_id','user_id'):
                await call(f'FIX01-employee-sensitive-{uid}-{label}-{field}',uid,'PUT','/employees/1',{field:None},media,403)
            await call(f'FIX01-employee-fact-{uid}-{label}',uid,'PUT','/employees/1',{'remark':f'SYNTHETIC-{uid}-{label}'},media)
        for label,media in INVALID:
            await call(f'FIX01-employee-invalid-media-{uid}-{label}',uid,'PUT','/employees/1',{'remark':'SYNTHETIC'},media,415 if label == 'empty' else 422)
    # Form whitelists are selected from declared route fields, not media spelling.
    from urllib.parse import urlencode
    for label,media in [('form-standard','application/x-www-form-urlencoded'),('form-space','application/x-www-form-urlencoded ; charset=utf-8'),('form-case','Application/X-Www-Form-Urlencoded')]:
        await call(f'FIX01-{label}-unknown-clock-field',3,'POST','/clock-in',media=media,raw=urlencode({'session':'1','status':'approved'}).encode(),expected=400)
        await call(f'FIX01-{label}-unknown-leave-field',3,'POST','/attendance/leaves?view=self',media=media,raw=urlencode({'leave_date':'2026-10-27','status':'approved'}).encode(),expected=400)
    (out/'media-status.json').write_text(json.dumps({'marker':'permissions7-r04-fix01-20261028','requests':len(records),'failures':failures},ensure_ascii=False,indent=2))
    if failures: raise AssertionError(failures)
