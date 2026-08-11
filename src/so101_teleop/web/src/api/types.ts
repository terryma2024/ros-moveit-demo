export type StepFrame = "WORLD" | "TOOL";

export type Pose6D = {
  frame_id: string;
  tcp_frame: string;
  x_m: number;
  y_m: number;
  z_m: number;
  roll_rad: number;
  pitch_rad: number;
  yaw_rad: number;
};

export type JointSample = { name?: string; position_rad: number; velocity_rad_s: number; lower_limit_rad?: number | null; upper_limit_rad?: number | null };

export type TelemetrySnapshot = {
  sequence: number;
  revision: number;
  simulation_session_id: string;
  mode?: string;
  environment?: Record<string, string>;
  joints: Record<string, JointSample>;
  tcp?: Pose6D;
  [key: string]: unknown;
};

export type ReplayableTarget = {
  step_frame: StepFrame;
  joints_rad: Record<string, number>;
  tcp: Pose6D;
};

export type CommandResult = {
  code: string;
  succeeded: boolean;
  message?: string;
  snapshot_revision?: number;
  layers?: Record<string, string>;
  data?: Record<string, unknown>;
};

export type BackendCapabilityMap = {
  backend_probe: boolean;
  workflow_execute: boolean;
  workflow_start: boolean;
  workflow_run: boolean;
  workflow_resume: boolean;
  workflow_stop: boolean;
  reset_world: boolean;
  scene_operations: boolean;
  physical_observation: boolean;
  manual_joint_execute: boolean;
  manual_tcp_execute: boolean;
  camera_presets: boolean;
};

export type BackendCapabilities = {
  backend: "gazebo_cpp" | "gazebo_py" | "mujoco_py";
  owner_package: string;
  owner_executable: string;
  capabilities: BackendCapabilityMap;
};
