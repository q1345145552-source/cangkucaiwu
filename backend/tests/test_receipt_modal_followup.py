"""Receipt-only regression on disposable loopback schemas; no real accounts or orders."""
import asyncio, json, os
from pathlib import Path
from sqlalchemy import select, func
from app.models import PurchaseReceiptEvent, PurchaseOrder, SystemSetting
from tests.test_supplier_receipts_round3 import fixture, order, receive, detail
from tests.test_supplier_workflow_round1 import request


def test_approved_order_photo_failures_retry_and_committed_state(tmp_path, monkeypatch):
    async def run():
        async with fixture(tmp_path, monkeypatch) as (_, factory, client):
            async with factory() as db:
                db.add(SystemSetting(warehouse_id=1,key='purchase_approval_threshold',value='0'))
                await db.commit()
            po = await order(client, quantity=3)
            assert po['status'] == 'pending'
            approved = await request(client,'PUT',f'/suppliers/purchase-approvals/{po["id"]}/approve')
            before = await detail(client,po)
            assert before['status'] == 'confirmed' and before['receipt_status'] == 'not_received'
            wrong = await receive(client,po,3,key='wrong-format',photo=b'not a photo',code=400)
            huge = await receive(client,po,3,key='huge-photo',photo=b'x'*(10*1024*1024+1),code=400)
            import app.services.image_utils as images
            original = images.save_image
            def broken(*args, **kwargs): raise OSError('synthetic disk failure')
            monkeypatch.setattr(images,'save_image',broken)
            storage = await receive(client,po,3,key='safe-original-request',code=500)
            async with factory() as db:
                assert await db.scalar(select(func.count()).select_from(PurchaseReceiptEvent)) == 0
                assert (await db.get(PurchaseOrder,po['id'])).receipt_status == 'not_received'
            monkeypatch.setattr(images,'save_image',original)
            result = await receive(client,po,3,key='safe-original-request')
            replay = await receive(client,po,3,key='safe-original-request')
            after = await detail(client,po)
            assert result['receipt_status'] == after['receipt_status'] == 'received'
            assert result['photo_path'] and result['items'][0]['received_quantity'] == 3
            assert replay['receipt_event_id'] == result['receipt_event_id']
            async with factory() as db:
                records = (await db.execute(select(PurchaseReceiptEvent))).scalars().all()
                assert len(records) == 1 and records[0].photo_path == result['photo_path']
            assert '图片上传失败' in wrong['detail'] and '10MB' in huge['detail'] and '图片上传失败' in storage['detail']
            evidence = dict(approved=approved,before=before,invalid=wrong,oversize=huge,storage_failure=storage,response=result,retry=replay,after=after,receipt_record_count=1)
            output=os.environ.get('RECEIPT_MODAL_REPORT')
            if output: Path(output).write_text(json.dumps(evidence,ensure_ascii=False,indent=2,default=str))
    asyncio.run(run())
