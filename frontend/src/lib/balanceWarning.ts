export function balanceWarningText(balance:unknown,amount:unknown):string|null {
 if(balance===null||balance===undefined)return null;
 const before=Number(balance),value=Number(amount);
 if(!Number.isFinite(before)||!Number.isFinite(value)||value<=0||before>=value)return null;
 const fmt=(n:number)=>n.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
 return `当前账户余额不足（可用 ${fmt(before)}，本次 ${fmt(value)}），确认继续吗`;
}
export function confirmBalanceWarning(balance:unknown,amount:unknown,confirm:(message:string)=>boolean=message=>window.confirm(message)):boolean {
 const message=balanceWarningText(balance,amount);
 return message===null||confirm(message);
}
