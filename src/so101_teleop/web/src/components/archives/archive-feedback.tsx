import type { ReactNode } from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Empty, EmptyDescription, EmptyHeader } from '@/components/ui/empty';

export function ArchiveNotice({children,error=false}:{children:ReactNode;error?:boolean}) {
  return <Alert variant={error?'destructive':'default'} role={error?'alert':'status'}><AlertDescription>{children}</AlertDescription></Alert>;
}
export function ArchiveEmpty({children}:{children:ReactNode}) {
  return <Empty className="border"><EmptyHeader><EmptyDescription>{children}</EmptyDescription></EmptyHeader></Empty>;
}
