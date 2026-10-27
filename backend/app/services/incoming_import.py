"""Chinese template mapping using the existing receipt validation/account rules."""
from datetime import datetime, date
import hashlib
from fastapi import HTTPException
from pydantic import ValidationError
from app.services.excel_import import table
from app.services.incoming_receipts import request_values
from app.services.wallet import read_account
from app.schemas.business import IncomingCreate
from app.services.payable_creation import fingerprint

HEADERS = {'到账日期':'received_date','金额':'amount','币种':'currency','付款方':'payer_name','付款方式':'payment_method','备注':'remark','收款账户编号':'account_id'}
HEADERS.update({v:v for v in list(HEADERS.values())})

async def preview(db,wid,content,user):
    raw, errors = table(content,HEADERS,{'received_date','amount','currency','account_id'})
    rows=[]
    for number, value in raw:
        if value == dict(zip(['received_date','amount','currency','payer_name','payment_method','remark','account_id'], ['2026-07-01',5000,'THB','示例客户','银行转账','示例备注','请填写本仓同币种账户编号'])): continue
        try:
            when=value.get('received_date')
            if isinstance(when,(datetime,date)): when=when.isoformat()
            if not isinstance(when,str) or not when.strip(): raise HTTPException(400,'到账日期必填，请使用YYYY-MM-DD')
            account=value.get('account_id')
            if isinstance(account,bool) or account in (None,'') or not str(account).isdigit() or int(account)<=0:
                raise HTTPException(400,'收款账户编号必须明确填写本仓可用同币种账户编号；请在账户管理核对')
            currency=value.get('currency')
            if currency not in ('THB','CNY'): raise HTTPException(400,'币种请明确填写THB或CNY')
            if isinstance(value.get('amount'),bool): raise HTTPException(400,'金额必须为有效正数')
            item=IncomingCreate(**{**value,'received_date':when,'account_id':int(account),'request_key':'preview'})
            request_values(item)
            await read_account(db,wid,item.account_id,item.currency)
            rows.append({'row_number':number,**item.model_dump(exclude={'request_key'})})
        except (HTTPException,ValidationError,ValueError) as exc:
            message=str(exc.detail) if isinstance(exc,HTTPException) else '字段格式错误，请检查日期、正数金额及文字长度'
            errors.append({'row_number':number,'message':message})
    if not raw or not rows and not errors: errors.append({'row_number':2,'message':'没有实际数据，空模板或只有示例行'})
    result={'mode':'preview','rows':rows,'errors':errors,'valid':not errors,'imported':0,'warehouse_id':wid,'operator_id':user.id,
            'message':'预览成功，尚未登记到账' if not errors else '校验失败，整批未保存'}
    result['preview_version']=fingerprint({'content_sha256':hashlib.sha256(content).hexdigest(),**result})
    return result
