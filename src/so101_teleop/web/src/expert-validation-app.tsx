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
import { TopViewMap } from "@/components/expert-validation/top-view-map";
import fixture from "@/fixtures/top_view_projection_v1.json";

export type ExpertValidationApi = {
  capabilities(): Promise<Capabilities>;
  acquireLease(serviceSessionId: string): Promise<Lease>;
  renewLease(lease: Lease): Promise<Lease>;
  createManifest(totalPoints: number): Promise<Manifest>;
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

function stableSessionId(): string {
  const key = "so101-expert-validation-service-session";
  const existing = sessionStorage.getItem(key);
  if (existing) return existing;
  const value = globalThis.crypto?.randomUUID?.() ?? `browser-${Date.now()}`;
  sessionStorage.setItem(key, value);
  return value;
}

export function ExpertValidationApp({ api = defaultClient }: { api?: ExpertValidationApi }) {
  const [capabilities, setCapabilities] = useState<Capabilities>();
  const [lease, setLease] = useState<Lease>();
  const leaseRef = useRef<Lease>();
  const receiptGeneration = useRef<number>();
  const [leaseRenewing, setLeaseRenewing] = useState(false);
  const [manifest, setManifest] = useState<Manifest>();
  const [receipt, setReceipt] = useState<PreflightReceipt>();
  const [campaign, setCampaign] = useState<CampaignView | null>(null);
  const [selectedPointId, setSelectedPointId] = useState<string>();
  const [notice, setNotice] = useState("");
  const [setup, setSetup] = useState<SetupState>({
    pointCount: 20,
    executionMode: "SEQUENTIAL",
    workerCount: 1,
    maxPointsPerWorker: 20,
  });
  const sessionId = useMemo(stableSessionId, []);

  const replaceLease = (next?: Lease) => {
    leaseRef.current = next;
    setLease(next);
    setReceipt(undefined);
    receiptGeneration.current = undefined;
  };

  const reportError = (error: unknown) => {
    setReceipt(undefined);
    setNotice(error instanceof Error ? error.message : String(error));
  };

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
      if (!value || disposed) return;
      setCampaign(value);
    });
    return () => {
      disposed = true;
    };
  }, [api]);

  useEffect(() => {
    if (!campaign) return;
    return api.watchCampaign?.(campaign.campaign_id, campaign.sequence, setCampaign);
  }, [api, campaign?.campaign_id]);

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
    setCampaign(result);
  };

  const changeSetup = (next: SetupState, field: keyof SetupState) => {
    setSetup(next);
    setReceipt(undefined);
    if (field === "pointCount") setManifest(undefined);
  };

  const mapCampaign = {
    points: fixture.points.map((point) => {
      const projected = campaign?.points?.find((candidate) => candidate.point_id === point.id);
      return {
        point_id: point.id,
        status: (projected?.status === "PASSED" || projected?.status === "FAILED"
          ? projected.status
          : "ELIGIBLE_UNRUN") as "PASSED" | "FAILED" | "ELIGIBLE_UNRUN",
        active_worker_id: projected?.active_worker_id ?? undefined,
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
        onGenerate={() => api.createManifest(setup.pointCount).then((value) => { setManifest(value); setReceipt(undefined); })}
        onPreflight={() => { void runPreflight().catch(reportError); }}
        onStart={() => { void start().catch(reportError); }}
      />
      {campaign ? (
        <div className="grid gap-5 lg:grid-cols-2">
          <TopViewMap manifest={fixture} campaign={mapCampaign} selectedPointId={selectedPointId} onSelect={setSelectedPointId} />
          <CampaignProgress campaign={campaign} />
        </div>
      ) : null}
      {selectedPoint ? <PointEvidence point={selectedPoint} artifacts={[]} /> : null}
      {campaign ? (
        <RetryPanel
          campaign={campaign}
          onRetry={async (pointIds, confirmation) => {
            const result = await api.retry(campaign.campaign_id, pointIds, authority(), confirmation);
            setCampaign(result);
          }}
        />
      ) : null}
    </main>
  );
}
