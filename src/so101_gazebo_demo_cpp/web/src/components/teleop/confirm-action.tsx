import { useState } from "react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

export function ConfirmAction({ label, onConfirm, disabled = false, evidence, typedConfirmation }: { label: string; onConfirm: () => void; disabled?: boolean; evidence?: string; typedConfirmation?: string }) {
  const [typed, setTyped] = useState("");
  const allowed = !typedConfirmation || typed === typedConfirmation;
  return <AlertDialog><AlertDialogTrigger asChild><Button variant="destructive" disabled={disabled}>{label}</Button></AlertDialogTrigger><AlertDialogContent><AlertDialogTitle className="text-lg font-semibold">Confirm {label}</AlertDialogTitle><AlertDialogDescription className="mt-2 text-slate-300">Simulation-side effect. Verify the target and convergence evidence before continuing.</AlertDialogDescription>{evidence && <pre className="mt-3 max-h-48 overflow-auto rounded border border-slate-700 p-3 text-xs">{evidence}</pre>}{typedConfirmation && <label className="mt-3 grid gap-1 text-sm">Type <code>{typedConfirmation}</code><input aria-label={`${label} confirmation`} value={typed} onChange={(event) => setTyped(event.target.value)}/></label>}<div className="mt-5 flex justify-end gap-2"><AlertDialogCancel asChild><Button variant="outline">Cancel</Button></AlertDialogCancel><AlertDialogAction asChild><Button variant="destructive" disabled={!allowed} onClick={onConfirm}>Confirm {label}</Button></AlertDialogAction></div></AlertDialogContent></AlertDialog>;
}
