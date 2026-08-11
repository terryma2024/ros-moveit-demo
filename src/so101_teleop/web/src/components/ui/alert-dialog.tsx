import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import { Button } from "@/components/ui/button";
export const AlertDialog=AlertDialogPrimitive.Root; export const AlertDialogTrigger=AlertDialogPrimitive.Trigger;
export const AlertDialogContent=({children}:{children:React.ReactNode})=><AlertDialogPrimitive.Portal><AlertDialogPrimitive.Overlay className="fixed inset-0 bg-black/70"/><AlertDialogPrimitive.Content className="fixed left-1/2 top-1/2 w-[min(92vw,32rem)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-slate-600 bg-slate-950 p-6 shadow-2xl">{children}</AlertDialogPrimitive.Content></AlertDialogPrimitive.Portal>;
export const AlertDialogAction=AlertDialogPrimitive.Action; export const AlertDialogCancel=AlertDialogPrimitive.Cancel;
export const AlertDialogTitle=AlertDialogPrimitive.Title; export const AlertDialogDescription=AlertDialogPrimitive.Description; export { Button };
