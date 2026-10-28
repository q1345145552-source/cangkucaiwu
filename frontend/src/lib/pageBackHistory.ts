// Only entries known to this authenticated app session are eligible for history back.
// history.length alone also counts unrelated sites and cannot prove a safe app entry.
export const PAGE_BACK_STATE = '__warehousePageBackV1';
type Stamp = { scope: string; previous: string | null };
function eligible(path: string): boolean { return !['/', '/login'].includes(path.split(/[?#]/)[0]); }
export function installPageBackHistory(scope: string): () => void {
 const history=window.history, push=history.pushState, replace=history.replaceState;
 const current=()=>history.state?.[PAGE_BACK_STATE] as Stamp|undefined;
 const url=()=>window.location.pathname+window.location.search+window.location.hash;
 const state=(data: any, stamp: Stamp)=>({...((data&&typeof data==='object')?data:{}),[PAGE_BACK_STATE]:stamp});
 if(current()?.scope!==scope) replace.call(history,state(history.state,{scope,previous:null}),'');
 const pushWrapped: History['pushState']=function(data,unused,target){
  const previous=current()?.scope===scope&&eligible(url())?url():null;
  push.call(history,state(data,{scope,previous}),unused,target);
 };
 const replaceWrapped: History['replaceState']=function(data,unused,target){
  const previous=current()?.scope===scope?current()!.previous:null;
  replace.call(history,state(data,{scope,previous}),unused,target);
 };
 history.pushState=pushWrapped;history.replaceState=replaceWrapped;
 return ()=>{if(history.pushState===pushWrapped)history.pushState=push;if(history.replaceState===replaceWrapped)history.replaceState=replace;};
}
export function hasAppBackHistory(scope: string): boolean {
 const stamp=window.history.state?.[PAGE_BACK_STATE] as Stamp|undefined;
 return stamp?.scope===scope && typeof stamp.previous==='string' && stamp.previous.startsWith('/') && !stamp.previous.startsWith('//') && eligible(stamp.previous);
}
