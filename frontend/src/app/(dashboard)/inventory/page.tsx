import {Suspense} from 'react';
import InventoryBoard from '@/components/InventoryBoard';
export default function Page(){return <Suspense fallback={<p>库存读取中</p>}><InventoryBoard/></Suspense>;}
