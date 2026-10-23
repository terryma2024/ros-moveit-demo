import * as React from 'react';
import { Progress as ProgressPrimitive } from 'radix-ui';
import { cn } from '@/lib/utils';

export const Progress=React.forwardRef<React.ElementRef<typeof ProgressPrimitive.Root>,React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>>(
  ({className,value=0,...props},ref)=><ProgressPrimitive.Root ref={ref} data-slot="progress" className={cn('relative h-2 w-full overflow-hidden rounded-full bg-secondary',className)} value={value} {...props}>
    <ProgressPrimitive.Indicator className="h-full w-full flex-1 bg-primary transition-transform" style={{transform:`translateX(-${100-(value??0)}%)`}}/>
  </ProgressPrimitive.Root>
);
Progress.displayName='Progress';
