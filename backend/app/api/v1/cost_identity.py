"""Read-only origin evidence; every origin uses its original module permission."""
import json
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from app.database import get_db
from app.models import CostIdentity,Supplier,ExpenseFundItem,ExpenseFund
from app.core.permissions import check_staff_permission_any,require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.services.supplier_payable_read import current_supplier_warehouse
from app.services import cost_identity as costs

router=APIRouter(dependencies=[Depends(require_non_labor)])
user_dependency=check_staff_permission_any(*(MENU_PERMISSIONS_BY_KEY[k].label for k in ('payable','payment_plans','expense_approval','expense_fund','operating')))

@router.get('/suppliers')
async def suppliers(user=Depends(user_dependency),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
    rows=(await db.execute(select(Supplier).where(Supplier.warehouse_id==wid).order_by(Supplier.id))).scalars()
    return {'data':[{'id':r.id,'name':r.name} for r in rows]}

@router.get('/{source}/{source_id}')
async def origin(source:str,source_id:int,voucher_index:int|None=Query(default=None,ge=0),user=Depends(user_dependency),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
    if source not in costs.MODELS:raise HTTPException(404,'费用来源不存在')
    if not costs.readable(user,source):raise HTTPException(403,'没有原单所属模块的查看权限')
    record=await db.get(costs.MODELS[source],source_id)
    root=(await db.execute(select(CostIdentity).where(CostIdentity.warehouse_id==wid,
        CostIdentity.source_type==source,CostIdentity.source_id==source_id))).scalar_one_or_none()
    if record:
        data=await costs.source_data(db,source,record)
        if data['warehouse_id']!=wid:raise HTTPException(404,'当前仓库未找到此费用来源')
        if record.cost_identity_id and root is None:
            root=await db.get(CostIdentity,record.cost_identity_id)
            if not root or root.warehouse_id!=wid:raise HTTPException(409,'费用来源关联异常')
            if not costs.readable(user,root.source_type):
                if voucher_index is not None:raise HTTPException(403,'没有原费用凭证的查看权限')
                return {'source':source,'id':source_id,'label':costs.LABELS[source],
                    'document':{k:str(v) for k,v in data.items()},'message':'这是其他业务生成的子记录；没有原费用权限，不展示原单信息'}
        document={**data,'description':getattr(record,'purpose',getattr(record,'description',getattr(record,'remark',None))),
            'number':getattr(record,'bill_number',None),'voucher':getattr(record,'bill_attachment',getattr(record,'voucher_path',getattr(record,'receipt',getattr(record,'voucher',None))))}
    elif root and root.source_deleted:document={**costs.values(root),'description':'原行已删除，已付费用身份及留痕保留，不能重复登记'}
    else:raise HTTPException(404,'当前仓库未找到此费用来源')
    if voucher_index is not None:
        # Read only this authorized record's exact attachment. Legacy non-warehouse
        # paths stay private; this does not widen the generic /uploads policy.
        from app.api.secure_uploads import upload_root
        raw=document.get('voucher')
        try:paths=json.loads(raw) if isinstance(raw,str) and raw.startswith('[') else raw if isinstance(raw,list) else [raw] if raw else []
        except (ValueError,TypeError):paths=[]
        if not isinstance(paths,list) or voucher_index>=len(paths):raise HTTPException(404,'原单凭证不存在')
        value=paths[voucher_index]
        if not isinstance(value,str) or value.startswith('//'):raise HTTPException(404,'原单凭证路径无效')
        parts=Path(value.lstrip('/')).parts
        if not parts or parts[0]!='uploads' or '..' in parts:raise HTTPException(404,'原单凭证路径无效')
        # A path explicitly belonging to another warehouse is never served.
        if len(parts)>1 and parts[1].isdigit() and int(parts[1])!=wid:raise HTTPException(404,'原单凭证不属于当前仓库')
        root_path=upload_root();file_path=root_path.joinpath(*parts[1:]).resolve()
        if not file_path.is_relative_to(root_path) or file_path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.pdf') or not file_path.is_file():raise HTTPException(404,'原单凭证不存在')
        return FileResponse(file_path,headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
    return {'source':source,'id':source_id,'label':costs.LABELS[source],'document':document,
        'identity':costs.metadata(root),'origin':None if root is None else {'source':root.source_type,'id':root.source_id},
        'message':'历史身份未记录，未补造供应商或发票' if root is None else '这是原费用来源；分期付款和派生记录不会另占一份发票' if (root.source_type,root.source_id)==(source,source_id) else '子记录与原业务共用费用身份，不是第二笔费用'}
