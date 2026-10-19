const assert=require('node:assert/strict');
const {harness,walk,text,find,button,change}=require('./fund-disbursement.test.cjs');
const labelled=(t,s)=>find(t,n=>n.props?.['aria-label']===s);
async function ready(options={}){
 const h=harness(options);let t=await h.render();await button(t,'充值').props.onClick();t=await h.render();
 change(find(t,n=>n.type==='input'&&n.props.placeholder==='输入金额'),'10000');t=await h.render();await button(t,'确认充值').props.onClick();t=await h.render();
 await button(t,'开销').props.onClick();t=await h.render();change(find(t,n=>n.type==='input'&&n.props.type==='number'&&n.props.value===''),'2000');t=await h.render();return{h,t};
}
function choose(t,camera=false){find(t,n=>n.type==='input'&&n.props.id===(camera?'receiptCameraInput4':'receiptFileInput4')).props.onChange({target:{files:[new Blob(['photo'],{type:'image/png'})]}});}
(async()=>{
 let {h,t}=await ready();assert(text(t).includes('凭证照片（必填）'));assert(text(t).includes('必须上传凭证，没有凭证不能报销'));
 await button(t,'保存').props.onClick();assert.equal(h.writes.length,1);assert.equal(h.uploads.length,0);assert(h.messages.some(m=>m[1]==='请上传开销凭证'));
 choose(t);t=await h.render();await button(t,'保存').props.onClick();t=await h.render();assert.deepEqual(h.events,['upload','create']);assert.equal(h.items.length,1);
 assert(h.uploads[0].url.endsWith('/accounts/1/upload-receipt'));assert.equal(h.uploads[0].opts.headers['X-Warehouse-ID'],'1');assert.equal(h.writes[1].body.receipt,'/uploads/fund_receipts/1/1/test.png');
 const row=find(t,n=>n.type==='tr'&&typeof n.props?.onClick==='function');await row.props.onClick();t=await h.render();
 labelled(t,'查看开销 #8 凭证').props.onClick();t=await h.render();assert.equal(find(t,n=>n.type==='img'&&n.props.alt==='开销凭证').props.src,h.items[0].receipt);
 assert.equal(find(t,n=>n.type==='a'&&text(n)==='查看原图').props.href,h.items[0].receipt);
 labelled(t,'关闭凭证大图').props.onClick();t=await h.render();labelled(t,'查看明细开销 #8 凭证').props.onClick();t=await h.render();assert(text(t).includes('凭证查看'));
 // Camera and photo-library controls both select images; camera uses the rear-camera hint.
 ({h,t}=await ready());button(t,'拍照').props.onClick();button(t,'相册 / 文件').props.onClick();assert.deepEqual(h.fileClicks,['receiptCameraInput4','receiptFileInput4']);
 assert.equal(find(t,n=>n.props?.id==='receiptCameraInput4').props.capture,'environment');choose(t,true);t=await h.render();await button(t,'保存').props.onClick();assert.equal(h.items.length,1);
 ({h,t}=await ready({uploadFail:true}));choose(t);t=await h.render();await button(t,'保存').props.onClick();t=await h.render();assert.equal(h.items.length,0);assert.equal(h.writes.length,1);assert(h.messages.some(m=>m[1]==='凭证上传失败'));assert.equal(button(t,'保存').props.disabled,false);
 ({h,t}=await ready({createFail:true}));choose(t);t=await h.render();await button(t,'保存').props.onClick();assert.equal(h.items.length,0);assert(h.messages.some(m=>m[1]==='余额不足'));
 ({h,t}=await ready({holdUpload:true}));choose(t);t=await h.render();const pending=button(t,'保存').props.onClick();t=await h.render();assert.equal(button(t,'保存中...').props.disabled,true);await button(t,'保存中...').props.onClick();assert.equal(h.uploads.length,1);h.releaseUpload();await pending;assert.equal(h.items.length,1);
 console.log('PASS: required receipt guard, upload-before-create, warehouse header, list/detail full image, original image link, camera/photo controls, upload/create failure and duplicate submit guard');
})().catch(e=>{console.error(e);process.exitCode=1;});
