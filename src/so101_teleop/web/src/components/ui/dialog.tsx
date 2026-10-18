import * as React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

export const Dialog=DialogPrimitive.Root;
export const DialogTrigger=DialogPrimitive.Trigger;
export const DialogClose=DialogPrimitive.Close;
export const DialogContent=React.forwardRef<React.ElementRef<typeof DialogPrimitive.Content>,React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>>(
  ({className,children,...props},ref)=><DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50"/>
    <DialogPrimitive.Content ref={ref} data-slot="dialog-content" className={cn('fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[min(95vw,60rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 rounded-lg border bg-background p-5 shadow-xl',className)} {...props}>
      {children}
      <DialogPrimitive.Close aria-label="Dismiss dialog" className="absolute right-3 top-3 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"><X aria-hidden="true" className="h-4 w-4"/></DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
);
DialogContent.displayName='DialogContent';
export function DialogHeader({className,...props}:React.ComponentProps<'div'>) {
  return <div data-slot="dialog-header" className={cn('shrink-0 space-y-2 pr-6 text-left',className)} {...props}/>;
}
export function DialogFooter({className,...props}:React.ComponentProps<'div'>) {
  return <div data-slot="dialog-footer" className={cn('flex shrink-0 flex-wrap justify-end gap-2',className)} {...props}/>;
}
export const DialogTitle=React.forwardRef<React.ElementRef<typeof DialogPrimitive.Title>,React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>>(
  ({className,...props},ref)=><DialogPrimitive.Title ref={ref} className={cn('break-all text-lg font-semibold leading-none tracking-tight',className)} {...props}/>
);
DialogTitle.displayName='DialogTitle';
export const DialogDescription=React.forwardRef<React.ElementRef<typeof DialogPrimitive.Description>,React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>>(
  ({className,...props},ref)=><DialogPrimitive.Description ref={ref} className={cn('break-all text-sm text-muted-foreground',className)} {...props}/>
);
DialogDescription.displayName='DialogDescription';
