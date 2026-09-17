import { useEffect, useMemo, useRef, useState } from "react";

import { ExpertValidationClient } from "@/api/expert-validation-client";
import type {
  CampaignProjection,
  Capabilities,
  ExecutionMode,
  Lease,
  LeaseAuthority,
  Manifest,
  PreflightInput,
  PreflightReceipt,
  StartCampaignInput,
} from "@/api/expert-validation-types";
import { CampaignProgress, type CampaignView } from "@/components/expert-validation/campaign-progress";
import { CampaignSetup, type SetupState } from "@/components/expert-validation/campaign-setup";
import { PointEvidence } from "@/components/expert-validation/point-evidence";
import { RetryPanel } from "@/components/expert-validation/retry-panel";
import { TopViewMap, type MapPointState } from "@/components/expert-validation/top-view-map";

export type ExpertValidationApi = {
  capabilities(): Promise<Capabilities>;
  acquireLease(serviceSessionId: string): Promise<Lease>;
  renewLease(lease: Lease): Promise<Lease>;
  createManifest(totalPoints: number): Promise<Manifest>;
  getManifest(manifestId: string): Promise<Manifest>;
  preflight(input: PreflightInput, lease: LeaseAuthority): Promise<PreflightReceipt>;
  startCampaign(input: StartCampaignInput, lease: LeaseAuthority): Promise<CampaignProjection>;
  retry(
    campaignId: string,
    pointIds: string[],
    lease: LeaseAuthority,
    confirmation: string,
  ): Promise<CampaignProjection>;
  restoreCampaign?(): Promise<CampaignView | null>;
  watchCampaign?(
    campaignId: string,
    after: number,
    apply: (campaign: CampaignProjection) => void,
  ): () => void;
};

const defaultClient = new ExpertValidationClient();

const TERMINAL_CAMPAIGNS = new Set([
  "COMPLETED", "COMPLETED_WITH_FAILURES", "INFRA_FAILED", "CLEANING_UP",
  "CANCELLED", "STOPPED", "NEEDS_OPERATOR_RECOVERY",
]);

function mapPointState(status: string | undefined, campaign: CampaignView | null): MapPointState {
  const terminal = TERMINAL_CAMPAIGNS.has(campaign?.status ?? "");
  if (campaign?.status === "NEEDS_OPERATOR_RECOVERY") return "INVALID_BLOCKED";
  if (status === "PASSED" || status === "FAILED" || status === "INDETERMINATE"
    || status === "INVALID_BLOCKED" || status === "TERMINAL_UNRUN"
    || status === "INFRA_FAILED_REMAINDER") return status;
  if (status === "INFRA_INTERRUPTED" || status === "INFRA_INTERRUPTED_REQUEUEABLE") {
    if (terminal) return "INFRA_FAILED_REMAINDER";
    return campaign?.execution_mode === "ADAPTIVE" ? "INFRA_INTERRUPTED_REQUEUEABLE" : "INVALID_BLOCKED";
  }
  if (status === "LEASED") return "LEASED";
  if (status === "RUNNING" || status === "EXECUTING") return "EXECUTING";
  if (!status || status === "UNRUN" || status === "ELIGIBLE_UNRUN") {
    return terminal ? "TERMINAL_UNRUN" : "ELIGIBLE_UNRUN";
  }
  return "INVALID_BLOCKED";
}

function stableSessionId(): string {
  const key = "so101-expert-validation-service-session";
  const existing = sessionStorage.getItem(key);
  if (existing) return existing;
  const value = globalThis.crypto?.randomUUID?.() ?? `browser-${Date.now()}`;
  sessionStorage.setItem(key, value);
  return value;
}

const LEASE_STORAGE_KEY = "so101-expert-validation-lease";

function storedLease(sessionId: string): Lease | undefined {
  const raw = sessionStorage.getItem(LEASE_STORAGE_KEY);
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw);
    if (
      typeof parsed?.lease_id !== "string" || !parsed.lease_id
      || parsed.service_session_id !== sessionId
      || !Number.isInteger(parsed.generation) || parsed.generation < 1
      || !Number.isInteger(parsed.expires_monotonic_ns)
    ) return undefined;
    return parsed as Lease;
  } catch {
    return undefined;
  }
}

export function ExpertValidationApp({ api = defaultClient }: { api?: ExpertValidationApi }) {
  const [capabilities, setCapabilities] = useState<Capabilities>();
  const [lease, setLease] = useState<Lease>();
  const leaseRef = useRef<Lease>();
  const receiptGeneration = useRef<number>();
  const [leaseRenewing, setLeaseRenewing] = useState(false);
  const [manifest, setManifest] = useState<Manifest>();
  const manifestRequestGeneration = useRef(0);
  const [campaignManifest, setCampaignManifest] = useState<Manifest>();
  const [mapError, setMapError] = useState("");
  const [receipt, setReceipt] = useState<PreflightReceipt>();
  const [campaign, setCampaign] = useState<CampaignView | null>(null);
  const campaignRef = useRef<CampaignView | null>(null);
  const [selectedPointId, setSelectedPointId] = useState<string>();
  const [notice, setNotice] = useState("");
  const [setup, setSetup] = useState<SetupState>({
    pointCount: 20,
    executionMode: "SEQUENTIAL",
    workerCount: 1,
    maxPointsPerWorker: 20,
  });
  const sessionId = useMemo(stableSessionId, []);

  const replaceCampaign = (next: CampaignView) => {
    campaignRef.current = next;
    setCampaign(next);
  };

  const replaceLease = (next?: Lease) => {
    leaseRef.current = next;
    setLease(next);
    if (next) sessionStorage.setItem(LEASE_STORAGE_KEY, JSON.stringify(next));
    else sessionStorage.removeItem(LEASE_STORAGE_KEY);
    setReceipt(undefined);
    receiptGeneration.current = undefined;
  };

  const reportError = (error: unknown) => {
    setReceipt(undefined);
    setNotice(error instanceof Error ? error.message : String(error));
  };

  // A page reload must not abandon the lease: the campaign outlives the tab's
  // React state, so reattach by renewing the lease persisted in this session.
  useEffect(() => {
    const stored = storedLease(sessionId);
    if (!stored) return;
    let disposed = false;
    api.renewLease(stored).then((renewed) => {
      if (disposed) return;
      if (renewed.lease_id !== stored.lease_id
        || renewed.service_session_id !== stored.service_session_id
        || renewed.generation <= stored.generation) {
        throw new Error("LEASE_RENEWAL_INVALID");
      }
      replaceLease(renewed);
    }).catch((error: unknown) => {
      if (disposed) return;
      sessionStorage.removeItem(LEASE_STORAGE_KEY);
      reportError(error);
    });
    return () => { disposed = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, sessionId]);

  useEffect(() => {
    if (!lease || !capabilities) return;
    let disposed = false;
    const duration = capabilities.lease_duration_s;
    const margin = capabilities.lease_renewal_margin_s;
    if (!Number.isFinite(duration) || !Number.isFinite(margin) || margin <= 0 || margin >= duration) {
      replaceLease();
      setNotice("LEASE_CAPABILITIES_INVALID");
      return;
    }
    const timer = setTimeout(() => {
      setLeaseRenewing(true);
      api.renewLease(lease).then((next) => {
        if (disposed) return;
        if (next.lease_id !== lease.lease_id || next.service_session_id !== lease.service_session_id
          || next.generation <= lease.generation || next.expires_monotonic_ns <= lease.expires_monotonic_ns) {
          throw new Error("LEASE_RENEWAL_INVALID");
        }
        setLeaseRenewing(false);
        replaceLease(next);
        setNotice("Lease renewed; check resources again");
      }).catch((error: unknown) => {
        if (disposed) return;
        setLeaseRenewing(false);
        replaceLease();
        reportError(error);
      });
    }, (duration - margin) * 1_000);
    return () => { disposed = true; clearTimeout(timer); };
  }, [api, lease, capabilities]);

  useEffect(() => {
    let disposed = false;
    api.capabilities().then(setCapabilities).catch(() => setNotice("Capabilities unavailable"));
    api.restoreCampaign?.().then((value) => {
      if (!value || disposed || campaignRef.current) return;
      replaceCampaign(value);
    }).catch((error: unknown) => { if (!disposed) reportError(error); });
    return () => {
      disposed = true;
      manifestRequestGeneration.current += 1;
    };
  }, [api]);

  useEffect(() => {
    if (!campaign) return;
    return api.watchCampaign?.(campaign.campaign_id, campaign.sequence, replaceCampaign);
  }, [api, campaign?.campaign_id]);

  useEffect(() => {
    let disposed = false;
    setCampaignManifest(undefined);
    setSelectedPointId(undefined);
    setMapError("");
    if (!campaign) return;
    const manifestId = campaign.manifest_id;
    if (!manifestId) { setMapError("CAMPAIGN_MANIFEST_ID_MISSING"); return; }
    api.getManifest(manifestId).then((value) => {
      if (disposed) return;
      if (value.manifest_id !== manifestId) throw new Error("CAMPAIGN_MANIFEST_ID_MISMATCH");
      if (!value.top_view) throw new Error("CAMPAIGN_MAP_NOT_AVAILABLE");
      setCampaignManifest(value);
    }).catch((error: unknown) => {
      if (!disposed) setMapError(error instanceof Error ? error.message : String(error));
    });
    return () => { disposed = true; };
  }, [api, campaign?.campaign_id, campaign?.manifest_id]);

  const authority = (): LeaseAuthority => {
    const current = leaseRef.current;
    if (!current) throw new Error("LEASE_REQUIRED");
    return {
      service_session_id: sessionId,
      lease_id: current.lease_id,
      lease_generation: current.generation,
    };
  };

  const preflightInput = (): PreflightInput => setup.executionMode === "ADAPTIVE"
    ? {
      manifest_id: manifest!.manifest_id,
      execution_mode: "ADAPTIVE",
      preferred_worker_count: 8,
      fallback_worker_counts: [6, 4, 2, 1],
      initial_points_per_worker: 3,
      worker_start_timeout_s: 120,
      max_infra_attempts_per_point: 5,
      yolo_executor_count: 2,
    }
    : {
      manifest_id: manifest!.manifest_id,
      execution_mode: setup.executionMode,
      worker_count: setup.workerCount,
      max_points_per_worker: setup.maxPointsPerWorker,
    };

  const runPreflight = async () => {
    if (!manifest || !leaseRef.current || leaseRenewing) return undefined;
    const boundAuthority = authority();
    const result = await api.preflight(preflightInput(), boundAuthority);
    if (leaseRef.current?.generation !== boundAuthority.lease_generation) {
      throw new Error("LEASE_CHANGED_DURING_PREFLIGHT");
    }
    receiptGeneration.current = boundAuthority.lease_generation;
    setReceipt(result);
    setNotice(result.admitted
      ? setup.executionMode === "PARALLEL" ? "Parallel admission passed" : "Preflight passed"
      : `Preflight rejected: ${result.reason_codes.join(", ")}`);
    return result;
  };

  const start = async () => {
    if (leaseRenewing || !leaseRef.current) return;
    const admitted = receipt && receiptGeneration.current === leaseRef.current.generation
      ? receipt : await runPreflight();
    if (!manifest || !admitted?.admitted) return;
    const result = await api.startCampaign(
      { ...preflightInput(), preflight_receipt_id: admitted.receipt_id } as StartCampaignInput,
      authority(),
    );
    replaceCampaign(result);
  };

  const changeSetup = (next: SetupState, field: keyof SetupState) => {
    setSetup(next);
    setReceipt(undefined);
    if (field === "pointCount") {
      manifestRequestGeneration.current += 1;
      setManifest(undefined);
    }
  };

  const generateManifest = async () => {
    const generation = ++manifestRequestGeneration.current;
    const count = setup.pointCount;
    const value = await api.createManifest(count);
    if (generation !== manifestRequestGeneration.current) return;
    if (value.point_count !== count || value.stale) throw new Error("GENERATED_MANIFEST_INVALID");
    setManifest(value);
    setReceipt(undefined);
  };

  const mapManifest = campaign
    ? campaignManifest?.manifest_id === campaign.manifest_id ? campaignManifest : undefined
    : manifest;
  const mapCampaign = {
    points: (mapManifest?.top_view?.points ?? []).map((point) => {
      const projected = campaign?.points?.find((candidate) => candidate.point_id === point.id);
      return {
        point_id: point.id,
        status: mapPointState(projected?.status, campaign),
        active_worker_id: projected?.active_worker_id ?? undefined,
        phase: campaign?.workers?.find((worker) => worker.worker_id === projected?.active_worker_id)?.state,
        reason: projected?.reason ?? undefined,
      };
    }),
  };
  const selectedPoint = campaign?.points?.find((point) => point.point_id === selectedPointId);

  return (
    <main className="mx-auto max-w-7xl space-y-5 p-6 text-slate-100">
      <header><h1 className="text-2xl font-bold">SO-101 Expert Validation</h1></header>
      <CampaignSetup
        capabilities={capabilities}
        state={setup}
        leaseHeld={Boolean(lease)}
        leaseRenewing={leaseRenewing}
        manifestReady={Boolean(manifest)}
        preflightMessage={notice}
        onChange={changeSetup}
        onAcquireLease={() => { void api.acquireLease(sessionId).then(replaceLease).catch(reportError); }}
        onGenerate={() => { void generateManifest().catch(reportError); }}
        onPreflight={() => { void runPreflight().catch(reportError); }}
        onStart={() => { void start().catch(reportError); }}
      />
      {campaign || mapManifest?.top_view ? (
        <div className="grid gap-5 lg:grid-cols-2">
          {mapManifest?.top_view ? <TopViewMap manifest={mapManifest.top_view} campaign={mapCampaign} selectedPointId={selectedPointId} onSelect={setSelectedPointId} />
            : <p role="status">Map unavailable: {mapError || "Loading bound manifest"}</p>}
          {campaign ? <CampaignProgress campaign={campaign} /> : null}
        </div>
      ) : null}
      {selectedPoint ? <PointEvidence point={selectedPoint} artifacts={selectedPoint.artifacts ?? []} /> : null}
      {campaign ? (
        <RetryPanel
          campaign={campaign}
          onRetry={async (pointIds, confirmation) => {
            const result = await api.retry(campaign.campaign_id, pointIds, authority(), confirmation);
            replaceCampaign(result);
          }}
        />
      ) : null}
    </main>
  );
}
