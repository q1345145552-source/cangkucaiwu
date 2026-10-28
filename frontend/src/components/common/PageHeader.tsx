"use client";
import { ArrowLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { ReactNode } from 'react';
import { useI18n } from '@/hooks/useI18n';
import { hasAppBackHistory } from '@/lib/pageBackHistory';
import type { PageParent } from '@/lib/pageParents';

/** Shared page heading: optional title/actions on the right, 44px back target on the left. */
export default function PageHeader({parent,scope,title,actions}:{parent:PageParent;scope:string;title?:ReactNode;actions?:ReactNode}) {
 const router=useRouter(),{t,locale}=useI18n();
 const name=parent.labelKey?t(parent.labelKey):parent.label;
 const label=locale==='zh'?`返回${name}`:t('page_back_to').replace('{page}',name);
 function back(){if(hasAppBackHistory(scope))window.history.back();else router.replace(parent.href);}
 return <div className="h-16 shrink-0 lg:h-auto" data-page-header="true">
  <div className="fixed top-14 left-0 right-0 z-40 flex min-h-[64px] items-center justify-between gap-3 border-b bg-white px-3 py-2 text-gray-900 lg:static lg:px-6">
   <button type="button" data-page-back="true" aria-label={label} onClick={back} className="inline-flex min-h-[44px] min-w-[44px] shrink-0 items-center gap-1 rounded-lg pr-3 text-sm text-blue-700 hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">
    <span className="flex h-11 w-11 shrink-0 items-center justify-center"><ArrowLeft size={20} aria-hidden="true" /></span><span>{label}</span>
   </button>
   {(title||actions)&&<div className="flex min-w-0 flex-wrap items-center justify-end gap-2">{title}{actions}</div>}
  </div>
 </div>;
}
