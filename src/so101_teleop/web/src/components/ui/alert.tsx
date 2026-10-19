import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export function Alert({className,variant='default',...props}:ComponentProps<'div'>&{variant?:'default'|'destructive'}) {
  return <div role="alert" data-slot="alert" className={cn('relative w-full rounded-lg border bg-background p-4 text-sm',variant==='destructive'?'border-destructive text-destructive':'text-foreground',className)} {...props}/>;
}
export function AlertDescription({className,...props}:ComponentProps<'div'>) {
  return <div className={cn('break-words leading-relaxed',className)} {...props}/>;
}
