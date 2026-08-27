import { useEffect, useMemo, useState } from "react";
import { Download, RefreshCw, ShieldCheck, Upload } from "lucide-react";
import { toast } from "sonner";

import { TaskApiClient } from "@/api/task-client";
import type { TaskPoint, TaskPointStatus, TaskRunSummary } from "@/api/task-types";
import { isCommandFailure } from "@/api/task-types";
import { TaskBuilder } from "@/components/tasks/task-builder";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { dumpTaskYaml, parseTaskYaml, validateTaskPoints } from "@/lib/task-yaml";

const client = new TaskApiClient();

export function TaskApp() {
  const [presets, setPresets] = useState<TaskPoint[]>([]);
  const [points, setPoints] = useState<TaskPoint[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [leaseId, setLeaseId] = useState("");
  const [run, setRun] = useState<TaskRunSummary>();
  const [reachability, setReachability] = useState<Record<string, TaskPointStatus>>({});
  const [notice, setNotice] = useState("Acquire the control lease, add points, then validate reachability.");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([client.snapshot(), client.presets(), client.runs()])
      .then(([snapshot, presetResponse, runs]) => {
        if (!active) return;
        setSessionId(snapshot.simulation_session_id);
        setPresets(presetResponse.points);
        const current = [...runs].reverse().find((candidate) => candidate.status === "RUNNING") ?? runs.at(-1);
        if (current) setRun(current);
      })
      .catch((error) => { if (active) setNotice(`Task API unavailable: ${String(error)}`); });
    return () => { active = false; };
  }, []);

  const inputError = useMemo(() => {
    try {
      validateTaskPoints(points);
      return "";
    } catch {
      return "TASK_POINT_INVALID";
    }
  }, [points]);
  const canMutate = Boolean(leaseId && sessionId) && !busy;
  const canSubmit = canMutate && !inputError;

  const guarded = async (operation: () => Promise<void>) => {
    if (!leaseId || !sessionId) {
      setNotice("LEASE_REQUIRED: acquire the current session lease first.");
      return;
    }
    setBusy(true);
    try {
      await operation();
    } catch (error) {
      setNotice(String(error));
      toast.error("Task request failed", { description: String(error) });
    } finally {
      setBusy(false);
    }
  };

  const acquireLease = async () => {
    const result = await client.acquireLease();
    if (!result.succeeded || !result.layers?.lease_id) {
      setNotice(`${result.code}: ${result.message ?? "lease unavailable"}`);
      return;
    }
    setLeaseId(result.layers.lease_id);
    setNotice(`Lease acquired for session ${sessionId}.`);
  };

  const validate = () => guarded(async () => {
    validateTaskPoints(points);
    const result = await client.validate(points, sessionId, leaseId);
    if (isCommandFailure(result)) {
      setNotice(`${result.code}: ${result.message ?? "reachability failed"}`);
      return;
    }
    setReachability(Object.fromEntries(result.reports.map((report) => [report.point_id, report.status])));
    setNotice(`Reachability ${result.status}.`);
  });

  const start = () => guarded(async () => {
    validateTaskPoints(points);
    const result = await client.start(points, sessionId, leaseId);
    if (isCommandFailure(result)) {
      setNotice(`${result.code}: ${result.message ?? "start failed"}`);
      return;
    }
    setRun(result);
    setNotice(`Batch ${result.run_id} started.`);
  });

  const refresh = async () => {
    if (!run) return;
    const result = await client.status(run.run_id);
    setRun(result);
    setNotice(`Batch ${result.run_id}: ${result.status}.`);
  };

  const cancel = () => guarded(async () => {
    if (!run) return;
    const result = await client.cancel(run.run_id, sessionId, leaseId);
    if (isCommandFailure(result)) setNotice(`${result.code}: ${result.message ?? "cancel failed"}`);
    else { setRun(result); setNotice(`Batch ${result.run_id}: ${result.status}.`); }
  });

  const recover = () => guarded(async () => {
    if (!run) return;
    const result = await client.recovery(run.run_id, "stop", sessionId, leaseId);
    if (isCommandFailure(result)) setNotice(`${result.code}: ${result.message ?? "recovery failed"}`);
    else { setRun(result); setNotice(`Recovery result: ${result.status}.`); }
  });

  const capture = () => guarded(async () => {
    const result = await client.capture(sessionId, leaseId);
    if (isCommandFailure(result)) setNotice(`${result.code}: ${result.message ?? "capture failed"}`);
    else setNotice(`Capture ${result.capture_id}: ${result.status}.`);
  });

  const shutdown = () => guarded(async () => {
    const result = await client.shutdown(sessionId, leaseId);
    if (isCommandFailure(result)) setNotice(`${result.code}: ${result.message ?? "shutdown failed"}`);
    else { setRun(result); setNotice(`Environment shutdown: ${result.status}.`); }
  });

  const importYaml = async (file: File | undefined) => {
    if (!file) return;
    try {
      setPoints(parseTaskYaml(await file.text()));
      setReachability({});
      setNotice(`Imported ${file.name}.`);
    } catch {
      setNotice("TASK_POINT_INVALID: imported YAML was rejected.");
    }
  };

  const exportYaml = () => {
    try {
      const url = URL.createObjectURL(new Blob([dumpTaskYaml(points)], { type: "application/yaml" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "so101-rgbd-task-points.yaml";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setNotice("TASK_POINT_INVALID: nothing valid to export.");
    }
  };

  return <main className="mx-auto min-h-screen max-w-[1500px] space-y-5 p-4 lg:p-7">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-400">SO-101 / MuJoCo / RGB-D</p>
        <h1 className="mt-1 text-3xl font-semibold">Perception Pick &amp; Place Tasks</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-400">Reuse one visible environment across ordered RESET_WORLD points. Every point runs plan-only reachability before motion and retains terminal evidence on failure.</p>
      </div>
      <div className="flex gap-2">
        <a href="/" className="inline-flex h-9 items-center rounded-md border border-slate-600 px-3 text-sm hover:bg-slate-800">Open Teleop</a>
        <Button onClick={acquireLease} variant={leaseId ? "secondary" : "default"}><ShieldCheck className="mr-2 h-4 w-4" />{leaseId ? "Lease acquired" : "Acquire lease"}</Button>
      </div>
    </header>

    <Card>
      <CardHeader>
        <CardTitle>Ordered task points</CardTitle>
        <CardDescription>Session {sessionId || "unavailable"}. Presets and free points share the same strict schema.</CardDescription>
      </CardHeader>
      <CardContent className="mt-4 space-y-4">
        <div className="flex flex-wrap gap-2">
          <label className="inline-flex h-9 cursor-pointer items-center rounded-md border border-slate-600 px-3 text-sm hover:bg-slate-800"><Upload className="mr-2 h-4 w-4" />Import YAML<input className="hidden" type="file" accept=".yaml,.yml,text/yaml" onChange={(event) => importYaml(event.target.files?.[0])} /></label>
          <Button type="button" variant="outline" onClick={exportYaml}><Download className="mr-2 h-4 w-4" />Export YAML</Button>
        </div>
        <TaskBuilder presets={presets} points={points} onChange={(next) => { setPoints(next); setReachability({}); }} reachability={reachability} />
        {inputError && <p role="alert" className="text-sm text-amber-400">{inputError}: add at least one unique, finite point before validation.</p>}
      </CardContent>
    </Card>

    <Card>
      <CardHeader><CardTitle>Task controls</CardTitle><CardDescription>All mutating actions require the current control lease.</CardDescription></CardHeader>
      <CardContent className="mt-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button disabled={!canSubmit} onClick={validate}>Validate reachability</Button>
          <Button disabled={!canSubmit || run?.status === "RUNNING"} onClick={start}>Start batch</Button>
          <Button variant="outline" disabled={!run} onClick={refresh}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button>
          <Button variant="destructive" disabled={!canMutate || run?.status !== "RUNNING"} onClick={cancel}>Cancel</Button>
          <Button variant="outline" disabled={!canMutate || run?.status !== "NEEDS_OPERATOR_RECOVERY"} onClick={recover}>Stop recovery</Button>
          <Button variant="outline" disabled={!canMutate} onClick={capture}>Capture sensor now</Button>
          <Button variant="destructive" disabled={!canMutate || !run} onClick={shutdown}>Shutdown owned environment</Button>
        </div>
        <p aria-live="polite" className="rounded bg-slate-950 p-3 text-sm text-slate-300">{notice}</p>
        {run && <div className="rounded border border-slate-700 p-3 text-sm"><strong>{run.run_id}</strong> · {run.status} · {run.points.length} point results</div>}
      </CardContent>
    </Card>
  </main>;
}
