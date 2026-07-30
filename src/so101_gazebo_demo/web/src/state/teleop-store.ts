import type { Pose6D, StepFrame, TelemetrySnapshot } from "@/api/types";

export type TeleopState = {
  actual: TelemetrySnapshot;
  target: { joints: Record<string, number>; tcp?: Pose6D; stepFrame: StepFrame; edited: boolean };
  plan: { id?: string; executable: boolean; staleCode?: string };
};

export type TeleopAction =
  | { type: "telemetry"; snapshot: TelemetrySnapshot }
  | { type: "edit-joint"; joint: string; value: number }
  | { type: "edit-tcp"; tcp: Pose6D }
  | { type: "set-step-frame"; frame: StepFrame }
  | { type: "current-to-target" }
  | { type: "plan-created"; planId: string }
  | { type: "plan-cleared" };

export function initialTeleopState(): TeleopState {
  return {
    actual: { sequence: -1, revision: 0, simulation_session_id: "", joints: {} },
    target: { joints: {}, stepFrame: "WORLD", edited: false },
    plan: { executable: false },
  };
}

function stalePlan(plan: TeleopState["plan"]): TeleopState["plan"] {
  return plan.id ? { ...plan, executable: false, staleCode: "PLAN_STALE_TARGET" } : plan;
}

export function reduceTeleop(state: TeleopState, action: TeleopAction): TeleopState {
  switch (action.type) {
    case "telemetry": {
      if (action.snapshot.sequence <= state.actual.sequence) return state;
      const first = state.actual.sequence < 0 && !state.target.edited;
      return {
        ...state,
        actual: action.snapshot,
        target: first ? {
          ...state.target,
          joints: Object.fromEntries(Object.entries(action.snapshot.joints).map(([joint, sample]) => [joint, sample.position_rad])),
          tcp: action.snapshot.tcp,
        } : state.target,
      };
    }
    case "edit-joint":
      return { ...state, target: { ...state.target, edited: true, joints: { ...state.target.joints, [action.joint]: action.value } }, plan: stalePlan(state.plan) };
    case "edit-tcp":
      return { ...state, target: { ...state.target, edited: true, tcp: action.tcp }, plan: stalePlan(state.plan) };
    case "set-step-frame":
      return { ...state, target: { ...state.target, edited: true, stepFrame: action.frame }, plan: stalePlan(state.plan) };
    case "current-to-target":
      return {
        ...state,
        target: {
          ...state.target,
          edited: false,
          joints: Object.fromEntries(Object.entries(state.actual.joints).map(([joint, sample]) => [joint, sample.position_rad])),
          tcp: state.actual.tcp,
        },
        plan: { executable: false },
      };
    case "plan-created":
      return { ...state, plan: { id: action.planId, executable: true } };
    case "plan-cleared":
      return { ...state, plan: { executable: false } };
  }
}
