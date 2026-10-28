"use client";
import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { getActiveWarehouseId } from '@/lib/api';
import { installPageBackHistory } from '@/lib/pageBackHistory';
import { pageParent } from '@/lib/pageParents';
import PageHeader from './PageHeader';

export default function PageNavigation(){
 const {user}=useAuth(),path=usePathname();
 const scope=user?`${user.id}:${user.role}:${getActiveWarehouseId()||user.warehouse_id||'platform'}`:'';
 useEffect(()=>scope?installPageBackHistory(scope):undefined,[scope]);
 if(!user)return null;
 const parent=pageParent(path,user.role);
 return parent?<PageHeader parent={parent} scope={scope}/>:null;
}
