import type { components } from "./expert-validation-schema";

type Schemas = components["schemas"];

export type ExecutionMode = Schemas["CampaignConfiguration"]["execution_mode"];
export type CampaignConfiguration = Schemas["CampaignConfiguration"];
export type CampaignStartRequest = Schemas["CampaignStartRequest"];
export type CampaignCancelRequest = Schemas["CampaignCancelRequest"];
export type RetryRequest = Schemas["RetryRequest"];
export type Capabilities = Schemas["CapabilitiesResponse"];
export type Lease = Schemas["LeaseResponse"];
export type Manifest = Schemas["ManifestResponse"];
export type ManifestPoint = Schemas["ManifestPointResponse"];
export type PreflightReceipt = Schemas["PreflightResponse"];
export type CampaignProjection = Schemas["CampaignProjectionResponse"];
export type PointProjection = Schemas["PointProjectionResponse"];
export type WorkerProjection = Schemas["WorkerProjectionResponse"];
export type BrokerProjection = Schemas["BrokerProjectionResponse"];
export type AttemptProjection = Schemas["AttemptProjectionResponse"];

export type LeaseAuthority = Pick<
  CampaignConfiguration,
  "service_session_id" | "lease_id" | "lease_generation"
>;

export type PreflightInput = Omit<
  CampaignConfiguration,
  "service_session_id" | "lease_id" | "lease_generation"
>;

export type StartCampaignInput = Omit<
  CampaignStartRequest,
  "service_session_id" | "lease_id" | "lease_generation" | "command_id"
>;

export type CampaignHint = Pick<CampaignProjection, "campaign_id" | "sequence">;
