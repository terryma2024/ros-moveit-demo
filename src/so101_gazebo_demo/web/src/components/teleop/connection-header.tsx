import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function ConnectionHeader({ mode, session, revision, leaseHeld, rttMs, onAcquire }: { mode: string; session: string; revision: number; leaseHeld: boolean; rttMs?: number; onAcquire: () => void }) {
  const metadata = `simulation-only · session ${session || "—"} · rev ${revision} · RTT ${rttMs === undefined ? "—" : `${rttMs.toFixed(0)} ms`}`;

  return (
    <header className="flex min-w-0 flex-wrap items-center gap-3 border-b border-slate-700 pb-4">
      <div aria-label="Primary connection actions" className="flex shrink-0 items-center gap-3">
        <h1 className="text-2xl font-bold">SO-101 Teleop</h1>
        <Badge className="border-sky-700 bg-sky-900 text-sky-100 hover:bg-sky-900">{mode}</Badge>
        <Button size="sm" variant={leaseHeld ? "outline" : "secondary"} disabled={leaseHeld} onClick={onAcquire}>
          {leaseHeld ? "Lease active" : "Acquire lease"}
        </Button>
      </div>
      <span aria-label="Connection metadata" className="min-w-0 flex-1 break-words text-sm text-slate-400 sm:truncate" title={metadata}>
        {metadata}
      </span>
    </header>
  );
}
