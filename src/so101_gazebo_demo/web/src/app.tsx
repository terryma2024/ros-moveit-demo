import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { toast } from "sonner";

import { TeleopApiClient } from "@/api/client";
import { isTelemetrySnapshot } from "@/api/telemetry-client";
import type { CommandResult, Pose6D, ReplayableTarget, TelemetrySnapshot } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CollisionPanel } from "@/components/teleop/collision-panel";
import { ConnectionHeader } from "@/components/teleop/connection-header";
import { EventLog, type EventEntry } from "@/components/teleop/event-log";
import { EnvironmentPanel } from "@/components/teleop/environment-panel";
import { GazeboPanel } from "@/components/teleop/gazebo-panel";
import { JointPanel } from "@/components/teleop/joint-panel";
import { TargetYamlControls } from "@/components/teleop/target-yaml-controls";
import { TcpPanel } from "@/components/teleop/tcp-panel";
import { WorkflowPanel } from "@/components/teleop/workflow-panel";
import { applyPoseStep } from "@/lib/units";
import { clampJointTarget } from "@/lib/joint-limits";
import { initialTeleopState, reduceTeleop } from "@/state/teleop-store";

type LiveSnapshot = TelemetrySnapshot & {
  mode: string;
  controllers: Record<string, string>;
  source_ages_s: Record<string, number>;
  object_pose?: Pose6D;
  gazebo_attached?: boolean;
  moveit_attached?: boolean;
  moveit_collisions: any[];
  gazebo_contacts: any[];
  real_time_factor?: number | null;
};

const client = new TeleopApiClient();

export function App() {
  const [state, dispatch] = useReducer(reduceTeleop, undefined, initialTeleopState);
  const [lease, setLease] = useState("");
  const [workflow, setWorkflow] = useState<any>();
  const [notice, setNotice] = useState("Acquire a control lease before planning.");
  const [shot, setShot] = useState("");
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [rttMs, setRttMs] = useState<number>();
  const [tcpPlanning, setTcpPlanning] = useState(false);
  const [cameraPresets, setCameraPresets] = useState<string[]>([]);
  const sessionRef = useRef("");
  const snapshot = state.actual as LiveSnapshot;
  const environment = snapshot.environment ?? {};

  const acceptSnapshot = useCallback((next: LiveSnapshot) => {
    if (sessionRef.current && sessionRef.current !== next.simulation_session_id) {
      setLease(""); setWorkflow(undefined); dispatch({ type: "plan-cleared" });
      setNotice("Simulation session changed; lease, plans and workflow were invalidated.");
    }
    sessionRef.current = next.simulation_session_id;
    dispatch({ type: "telemetry", snapshot: next });
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      const started = performance.now();
      try {
        const response = await fetch("/snapshot");
        if (!response.ok) throw new Error(`HTTP_${response.status}`);
        const next = await response.json() as LiveSnapshot;
        if (active) { setRttMs(performance.now() - started); acceptSnapshot(next); }
      } catch { if (active) setNotice("Telemetry API unavailable"); }
    };
    refresh();
    const timer = window.setInterval(refresh, 2000);
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const websocket = new WebSocket(`${protocol}://${location.host}/telemetry`);
    websocket.onmessage = (event) => {
      if (!active) return;
      try {
        const candidate = JSON.parse(event.data);
        if (isTelemetrySnapshot(candidate)) acceptSnapshot(candidate as LiveSnapshot);
      } catch {
        // Ignore non-JSON traffic from development WebSocket middleware.
      }
    };
    return () => { active = false; window.clearInterval(timer); websocket.close(); };
  }, [acceptSnapshot]);

  useEffect(() => {
    let active = true;
    fetch("/gazebo/camera/presets")
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`HTTP_${response.status}`)))
      .then((payload: { presets?: string[] }) => { if (active) setCameraPresets(payload.presets ?? []); })
      .catch(() => { if (active) setNotice("Camera presets unavailable"); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!lease) return;
    const timer = window.setInterval(async () => {
      const result = await client.post("/control/lease/renew", {}, lease, snapshot.simulation_session_id);
      if (!result.succeeded) {
        setLease(""); dispatch({ type: "plan-cleared" });
        setNotice(`${result.code}: ${result.message ?? "lease renewal failed"}`);
        toast.error(result.code, { description: result.message ?? "lease renewal failed" });
      }
    }, 10000);
    return () => window.clearInterval(timer);
  }, [lease, snapshot.simulation_session_id]);

  const record = (operation: string, result: CommandResult) => {
    setEvents((current) => [{ at: new Date().toISOString(), operation, code: result.code, message: result.message }, ...current].slice(0, 100));
    setNotice(`${result.code}${result.message ? `: ${result.message}` : ""}`);
    if (!result.succeeded && result.code) {
      toast.error(result.code, { description: result.message ?? "Command failed" });
    }
  };

  const call = async (path: string, body: Record<string, unknown> = {}) => {
    const result = await client.post(path, body, lease, snapshot.simulation_session_id);
    record(path, result);
    if (result.layers?.lease_id) setLease(result.layers.lease_id);
    if (result.layers?.plan_id) dispatch({ type: "plan-created", planId: result.layers.plan_id });
    const data = result.data as any;
    if (data?.workflow) setWorkflow({ ...data.workflow, snapshot_revision: result.snapshot_revision });
    return result;
  };

  const execute = async () => {
    if (!state.plan.id) return;
    const result = await call(`/plans/${state.plan.id}/execute`);
    if (result.succeeded) dispatch({ type: "plan-cleared" });
  };

  const executeAll = async () => {
    if (!state.plan.id) return;
    const result = await client.executeAll(state.plan.id, state.target.joints["6"], lease, snapshot.simulation_session_id);
    record("/execution/all:arm", result.arm);
    if (result.gripper) record("/execution/all:gripper", result.gripper);
    dispatch({ type: "plan-cleared" });
  };

  const workflowCommand = async (operation: string, body: Record<string, unknown> = {}) => {
    const confirmation = operation === "reset" ? { confirmation: "CONFIRM WORKFLOW_RESET" } : {};
    await call(`/workflow/${operation}`, { ...body, ...confirmation, run_id: workflow?.run_id });
  };

  const targetPose = state.target.tcp ?? { frame_id: "world", tcp_frame: "so101_tcp", x_m: 0, y_m: 0, z_m: 0, roll_rad: 0, pitch_rad: 0, yaw_rad: 0 };
  const replayableTarget: ReplayableTarget = { step_frame: state.target.stepFrame, joints_rad: state.target.joints, tcp: targetPose };
  const importTarget = (target: ReplayableTarget) => {
    dispatch({ type: "set-step-frame", frame: target.step_frame });
    const notices: string[] = [];
    Object.entries(target.joints_rad).forEach(([joint, value]) => {
      const result = clampJointTarget(joint, value, snapshot.joints[joint]);
      if (result.unavailable) {
        notices.push(`Joint ${joint} was not imported because safe limits are unavailable.`);
        return;
      }
      dispatch({ type: "edit-joint", joint, value: result.value });
      if (result.message) notices.push(result.message);
    });
    dispatch({ type: "edit-tcp", tcp: target.tcp });
    setNotice(notices.length ? notices.join(" ") : "Target YAML loaded in browser; no server file was written.");
  };
  const diagnosticSnapshot = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ captured_at: new Date().toISOString(), snapshot, target: replayableTarget, plan: state.plan, workflow, events }, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "so101-diagnostic-snapshot.json"; anchor.click(); URL.revokeObjectURL(url);
  };
  const planJoints = () => call("/plan/joints", {
    target_joints_rad: Object.fromEntries(
      ["1", "2", "3", "4", "5"].map((joint) => [joint, state.target.joints[joint]]),
    ),
  });
  const planTcp = async () => {
    if (tcpPlanning) return;
    setTcpPlanning(true);
    try {
      await call("/plan/tcp", { target: targetPose, step_frame: state.target.stepFrame });
    } finally {
      setTcpPlanning(false);
    }
  };

  return <main className="mx-auto min-w-0 max-w-7xl p-6">
    <ConnectionHeader mode={snapshot.mode ?? "STARTING"} session={snapshot.simulation_session_id} revision={snapshot.revision} leaseHeld={Boolean(lease)} rttMs={rttMs} onAcquire={() => call("/control/lease")}/>
    <div className="my-4 flex flex-wrap items-center gap-3"><p aria-live="polite" className="text-sky-200">{notice}</p><Button size="sm" variant="outline" onClick={() => dispatch({ type: "current-to-target" })}>Current to Target</Button><Button size="sm" variant="outline" onClick={diagnosticSnapshot}>Download diagnostic snapshot</Button><span className="text-sm text-slate-400">RTF {snapshot.real_time_factor == null ? "—" : snapshot.real_time_factor.toFixed(3)}</span></div>
    <Tabs defaultValue="joints" className="min-w-0">
      <TabsList aria-label="Teleop panel navigation" className="w-full max-w-full justify-start overflow-x-auto overflow-y-hidden bg-slate-900 text-slate-300">
        {([['joints', 'Joints'], ['tcp', 'TCP'], ['collision', 'Collision'], ['target', 'Target'], ['gazebo', 'Gazebo'], ['workflow', 'Workflow'], ['events', 'Events'], ['environment', 'Environment']] as const).map(([value, label]) => <TabsTrigger className="shrink-0 data-[state=active]:bg-sky-700 data-[state=active]:text-white" key={value} value={value}>{label}</TabsTrigger>)}
      </TabsList>
      <TabsContent value="joints"><JointPanel joints={snapshot.joints} targets={state.target.joints} leaseHeld={Boolean(lease)} plan={state.plan} onEdit={(joint, value) => dispatch({ type: "edit-joint", joint, value })} onClampNotice={setNotice} onPlan={planJoints} onExecute={execute} onExecuteGripper={() => call("/gripper/execute", { target_position_rad: state.target.joints["6"] })} onExecuteAll={executeAll} onCancel={() => call("/execution/cancel")}/></TabsContent>
      <TabsContent value="tcp"><TcpPanel pose={targetPose} frame={state.target.stepFrame} leaseHeld={Boolean(lease)} planning={tcpPlanning} plan={state.plan} onFrame={(frame) => dispatch({ type: "set-step-frame", frame })} onEdit={(tcp) => dispatch({ type: "edit-tcp", tcp })} onStep={(axis, direction) => dispatch({ type: "edit-tcp", tcp: applyPoseStep(targetPose, axis, direction, state.target.stepFrame) })} onPlan={planTcp} onExecute={execute} onCancel={() => call("/execution/cancel")}/></TabsContent>
      <TabsContent value="collision"><CollisionPanel
        moveit={(snapshot.moveit_collisions as import("@/components/teleop/collision-panel").Evidence[] | undefined) ?? []}
        gazebo={(snapshot.gazebo_contacts as import("@/components/teleop/collision-panel").Evidence[] | undefined) ?? []}
        objectPose={snapshot.object_pose as import("@/api/types").Pose6D | undefined}
        controllers={(snapshot.controllers as Record<string, string> | undefined) ?? {}}
        sourceAges={(snapshot.source_ages_s as Record<string, number> | undefined) ?? {}}
      /></TabsContent>
      <TabsContent value="target"><TargetYamlControls target={replayableTarget} onImport={importTarget} onError={setNotice}/></TabsContent>
      <TabsContent value="gazebo"><GazeboPanel leaseHeld={Boolean(lease)} gazeboAttached={snapshot.gazebo_attached} moveitAttached={snapshot.moveit_attached} shot={shot} cameraPresets={cameraPresets} onCameraPreset={(preset) => call(`/gazebo/camera/presets/${preset}`)} onScreenshot={async () => { const result = await call("/gazebo/screenshot"); const data = result.data as any; if (data?.url) setShot(data.url); }} onAttach={() => call("/attachment/attach")} onDetach={() => call("/attachment/detach")} onRepair={() => call("/scene/repair", { confirmation: "CONFIRM SCENE_REPAIR" })} onHome={() => call("/robot/home", { confirmation: "CONFIRM ROBOT_HOME" })} onReset={() => call("/simulation/reset", { confirmation: "CONFIRM SIMULATION_RESET" })}/></TabsContent>
      <TabsContent value="workflow"><WorkflowPanel snapshot={workflow} leaseHeld={Boolean(lease)} command={workflowCommand}/></TabsContent>
      <TabsContent value="events"><EventLog entries={events}/></TabsContent>
      <TabsContent value="environment"><EnvironmentPanel environment={environment}/></TabsContent>
    </Tabs>
  </main>;
}
