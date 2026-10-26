import {Suspense} from 'react';
import ProcurementReviewHistory from '@/components/ProcurementReviewHistory';
export default function Page(){return <Suspense fallback={<p>读取复核历史中</p>}><ProcurementReviewHistory/></Suspense>;}
