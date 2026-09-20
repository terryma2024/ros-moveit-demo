// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi, beforeEach } from "vitest";
import { DomainRuntime, type DomainTransport } from "@/state/domain-runtime";
import { RuntimeProvider } from "@/state/runtime-provider";

import { ExpertValidationApp, type ExpertValidationApi } from "./expert-validation-app";
import type { Lease, Manifest } from "@/api/expert-validation-types";
import golden from "@/fixtures/top_view_projection_v1.json";

beforeEach(() => {
  sessionStorage.removeItem("so101-expert-validation-lease");
});

function frozenManifest(count = 4, manifestId = "manifest-4"): Manifest {
  const points = golden.points.slice(0, count);
  return {
    manifest_id: manifestId, point_count: count, stale: false,
    points: points.map((point, index) => ({ ...point, label: point.id,
      source: index < 4 ? "anchor" : "generated", stratum: index < 4 ? "anchor" : point.id.split("_").slice(2).join("/"),
      position_world_m: point.position_world_m as [number, number, number] })),
    top_view: { ...golden,
      projection: { ...golden.projection, bounds_m: golden.projection.bounds_m as [number, number, number, number] },
      geometry: { ...golden.geometry,
        table_bounds: golden.geometry.table_bounds as [number, number, number, number],
        base_bounds: golden.geometry.base_bounds as [number, number, number, number],
        target_bounds: golden.geometry.target_bounds as [number, number, number, number],
        target_center: golden.geometry.target_center as [number, number],
        candidate_bounds: [-0.045, 0.08, -0.34, -0.24] },
      points: points.map(point => ({ ...point,
        position_world_m: point.position_world_m as [number, number, number],
        projected_px: point.projected_px as [number, number] })),
      palette: { blue: { ...golden.palette.blue, icon: "pending" },
        green: { ...golden.palette.green, icon: "passed" }, red: { ...golden.palette.red, icon: "failed" } },
    },
  };
}

/**
 * Render the app inside a root provider whose validation transport finishes renewals through the
 * test's own `renewLease` spy. Renewal is owned by the runtime, so the tests must drive the runtime
 * rather than expect the page to hold a timer.
 */
function renderWithRuntime(app: React.ReactElement, renewLease: (lease: Lease) => Promise<Lease>, cadenceMs = 20_000) {
  let lease: Lease | null = null;
  const transport: DomainTransport = {
    register: async (domain) => ({ instance_id: `i-${domain}`, proof: `p-${domain}`, domain }),
    connect: async (proof) => ({ instance_id: proof.instance_id, revision: 1, domain: proof.domain }),
    snapshot: async () => ({ sequence: 0, serviceEpoch: "e1", executionGeneration: 1, payload: null }),
    subscribe: () => () => undefined,
    renew: async () => {
      const current = lease ?? (runtime.lease() as unknown as Lease | null);
      if (!current) return undefined;
      const next = await renewLease(current);
      lease = next;
      return {
        lease_id: next.lease_id,
        service_session_id: next.service_session_id,
        generation: next.generation,
        expires_monotonic_ns: next.expires_monotonic_ns,
      };
    },
    setAuthority: () => undefined,
    // The acquire now goes through this transport, so it has to answer with a lease rather than a
    // placeholder: the page adopts whatever the transport returns.
    post: async () => ({
      lease_id: "L-acquired",
      service_session_id: "s1",
      generation: 1,
      expires_monotonic_ns: 10 ** 15,
    }),
    close: () => undefined,
  };
  const runtime = new DomainRuntime("validation", transport);
  const view = render(
    <RuntimeProvider validation={runtime}>
      {app}
    </RuntimeProvider>,
  );
  // The provider starts the runtime asynchronously; the heartbeat cadence matches the page's margin.
  void Promise.resolve().then(() => {
    runtime.adoptAuthority({ instanceId: "i-validation", proof: "p", channelRevision: 1, executionGeneration: 1 });
    runtime.startHeartbeat(cadenceMs);
  });
  return { ...view, runtime };
}

function fakeApi(overrides: Partial<ExpertValidationApi> = {}): ExpertValidationApi {
  return {
    async capabilities() {
      return {
        available: true,
        // The unified capabilities contract requires the per-N qualification view; until the
        // budget provider is integrated every exact N reports the fail-closed UNKNOWN view.
        worker_qualifications: [2, 3, 4, 5, 6, 7, 8].map((selected_n) => ({
          selected_n,
          status: "UNKNOWN",
          reasons: ["BUDGET_PROVIDER_NOT_READY"],
          runtime_identity: "test-runtime",
          contract_version: 2,
          profile_sha256: null,
          approval_sha256: null,
        })),
        execution_modes: ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"],
        default_execution_mode: "SEQUENTIAL",
        minimum_points: 4,
        maximum_points: 20,
        fixed_worker_counts: [1, 2, 3],
        worker_count_availability: [
          { worker_count: 2, selectable: true, status: "APPROVED", reason_codes: [] },
          { worker_count: 3, selectable: false, status: "NOT_MEASURED", reason_codes: ["BUDGET_PROFILE_UNAVAILABLE"] },
          { worker_count: 4, selectable: false, status: "NOT_MEASURED", reason_codes: ["BUDGET_PROFILE_UNAVAILABLE"] },
          { worker_count: 5, selectable: false, status: "NOT_MEASURED", reason_codes: ["BUDGET_PROFILE_UNAVAILABLE"] },
          { worker_count: 6, selectable: false, status: "NOT_MEASURED", reason_codes: ["BUDGET_PROFILE_UNAVAILABLE"] },
          { worker_count: 7, selectable: false, status: "NOT_MEASURED", reason_codes: ["BUDGET_PROFILE_UNAVAILABLE"] },
          { worker_count: 8, selectable: false, status: "NOT_MEASURED", reason_codes: ["BUDGET_PROFILE_UNAVAILABLE"] },
        ],
        adaptive_default_ladder: [8, 6, 4, 2, 1],
        lease_duration_s: 30,
        lease_renewal_margin_s: 10,
      };
    },
    async acquireLease(serviceSessionId) {
      return {
        lease_id: "lease-a",
        service_session_id: serviceSessionId,
        generation: 1,
        expires_monotonic_ns: 10_000,
      };
    },
    async renewLease(current) {
      return { ...current, generation: current.generation + 1, expires_monotonic_ns: current.expires_monotonic_ns + 30_000_000_000 };
    },
    async createManifest(totalPoints) {
      return frozenManifest(totalPoints, `manifest-${totalPoints}`);
    },
    async getManifest(manifestId) { return frozenManifest(4, manifestId); },
    async preflight(input) {
      return {
        receipt_id: "receipt-1",
        admitted: true,
        manifest_id: input.manifest_id,
        execution_mode: input.execution_mode,
        execution_config: input,
        resource_observations: { memory_pressure: "LOW" },
        reason_codes: [],
      };
    },
    async startCampaign(input) {
      return {
        campaign_id: "campaign-1",
        manifest_id: input.manifest_id,
        sequence: 1,
        execution_mode: "SEQUENTIAL",
        batch_cleanup_complete: false,
        points: [], workers: [], requested: 4, evaluated: 0, execution_started: 0,
        valid_succeeded: 0, valid_failed: 0, indeterminate: 0, not_executed: 4,
        evaluation_coverage: 0, execution_coverage: 0, levels_used: [],
        fallback_history: [], infra_attempts: 0, resource_observations: {},
      };
    },
    async retry() { throw new Error("not expected"); },
    ...overrides,
  };
}

describe("ExpertValidationApp", () => {
  test("restored map uses its bound four-point server document, not twenty golden coordinates or a new setup", async () => {
    const user = userEvent.setup();
    const frozen = frozenManifest();
    frozen.top_view!.points[0] = { ...frozen.top_view!.points[0],
      position_world_m: [0.03, -0.31, 0.165], projected_px: [640.2, 597.4] };
    const { container } = render(<ExpertValidationApp api={fakeApi({
      getManifest: async () => frozen,
      restoreCampaign: async () => ({ campaign_id: "campaign-1", manifest_id: "manifest-4",
        sequence: 4, status: "RUNNING", requested: 4,
        points: [{ point_id: "task_start", status: "UNRUN", retry_eligible: false,
          attempts: [], artifact_ids: [], artifacts: [] }] }),
    })} />);
    const marker = await screen.findByRole("button", { name: "P01 ELIGIBLE_UNRUN" });
    expect(container.querySelectorAll("[data-point-id]")).toHaveLength(4);
    expect(marker.getAttribute("transform")).toBe("translate(640.2 597.4)");
    await user.click(screen.getByRole("button", { name: "Generate points" }));
    expect(container.querySelectorAll("[data-point-id]")).toHaveLength(4);
    expect(marker.getAttribute("transform")).toBe("translate(640.2 597.4)");
  });

  test.each([
    ["RUNNING", "UNRUN", "blue", "SEQUENTIAL"],
    ["RUNNING", "INDETERMINATE", "red", "SEQUENTIAL"],
    ["RUNNING", "INFRA_INTERRUPTED", "red", "SEQUENTIAL"],
    ["RUNNING", "INFRA_INTERRUPTED", "blue", "ADAPTIVE"],
    ["INFRA_FAILED", "UNRUN", "red", "ADAPTIVE"],
    ["INFRA_FAILED", "INFRA_INTERRUPTED_REQUEUEABLE", "red", "ADAPTIVE"],
  ] as const)("map preserves authoritative point semantics for %s/%s", async (status, pointStatus, color, executionMode) => {
    render(<ExpertValidationApp api={fakeApi({ restoreCampaign: async () => ({
      campaign_id: "campaign-1", manifest_id: "manifest-4", sequence: 5, status, execution_mode: executionMode,
      points: [{ point_id: "task_start", status: pointStatus, retry_eligible: false,
        attempts: [], artifact_ids: [], artifacts: [] }],
    }) })} />);
    const marker = await screen.findByRole("button", { name: /^P01 / });
    expect(marker.getAttribute("data-color")).toBe(color);
  });

  test("failed bound-manifest read leaves progress visible without a fabricated map", async () => {
    render(<ExpertValidationApp api={fakeApi({
      getManifest: async () => { throw new Error("MANIFEST_NOT_FOUND"); },
      restoreCampaign: async () => ({ campaign_id: "campaign-1", manifest_id: "manifest-4", sequence: 5 }),
    })} />);
    expect(await screen.findByText(/MANIFEST_NOT_FOUND/)).toBeTruthy();
    expect(screen.queryByRole("img", { name: "Expert validation top view" })).toBeNull();
    expect(screen.getByRole("region", { name: "Campaign progress" })).toBeTruthy();
  });

  test("late map response cannot overwrite a replacement campaign's manifest", async () => {
    let apply: ((campaign: any) => void) | undefined;
    let release: ((manifest: Manifest) => void) | undefined;
    const oldManifest = new Promise<Manifest>((resolve) => { release = resolve; });
    const { container } = render(<ExpertValidationApp api={fakeApi({
      restoreCampaign: async () => ({ campaign_id: "old", manifest_id: "manifest-4", sequence: 1 }),
      getManifest: async (id) => id === "manifest-4" ? oldManifest : frozenManifest(20, id),
      watchCampaign: (_id, _sequence, update) => { apply = update; return () => {}; },
    })} />);
    await act(async () => {});
    await act(async () => { apply!({ campaign_id: "new", manifest_id: "manifest-20", sequence: 2 }); });
    await screen.findByRole("button", { name: "P20 ELIGIBLE_UNRUN" });
    await act(async () => { release!(frozenManifest()); });
    expect(container.querySelectorAll("[data-point-id]")).toHaveLength(20);
  });

  test("changing count while Generate is pending prevents stale preview resurrection", async () => {
    const user = userEvent.setup();
    let release: ((manifest: Manifest) => void) | undefined;
    const pending = new Promise<Manifest>((resolve) => { release = resolve; });
    render(<ExpertValidationApp api={fakeApi({ createManifest: async () => pending })} />);
    await user.click(await screen.findByRole("button", { name: "Acquire lease" }));
    await user.click(screen.getByRole("button", { name: "Generate points" }));
    fireEvent.change(screen.getByLabelText("Final point count"), { target: { value: "12" } });
    await act(async () => { release!(frozenManifest(20, "manifest-20")); });
    expect((screen.getByRole("button", { name: "Start validation" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("img", { name: "Expert validation top view" })).toBeNull();
  });

  test("selecting a committed point renders its typed sealed evidence rather than empty placeholders", async () => {
    const user = userEvent.setup();
    const image = {
      artifact_id: "opaque-rgb-a", campaign_id: "campaign-1", batch_id: "batch-1",
      worker_id: "worker-01", worker_generation: 2, attempt_id: "attempt-a",
      role: "task-rgb-before", media_type: "image/png", size_bytes: 68, sha256: "a".repeat(64),
    };
    const numeric = { ...image, artifact_id: "opaque-physical-a", role: "physical-evidence", media_type: "application/json" };
    render(<ExpertValidationApp api={fakeApi({ restoreCampaign: async () => ({
      campaign_id: "campaign-1", manifest_id: "manifest-4", sequence: 9, status: "COMPLETED",
      points: [{ point_id: "task_start", display_id: "P01", status: "PASSED",
        retry_eligible: false, attempts: [], artifact_ids: [image.artifact_id, numeric.artifact_id],
        artifacts: [image, numeric] }],
    }) })} />);
    await user.click(await screen.findByRole("button", { name: "P01 PASSED" }));
    expect((screen.getByAltText("task-rgb-before") as HTMLImageElement).src)
      .toContain("/expert-validation/artifacts/opaque-rgb-a");
    expect((screen.getByRole("link", { name: "Download physical-evidence" }) as HTMLAnchorElement).href)
      .toContain("/expert-validation/artifacts/opaque-physical-a");
    expect(screen.queryByText(/No committed evidence/)).toBeNull();
  });

  test("renewal at the server margin replaces stale preflight authority before start", async () => {
    vi.useFakeTimers();
    try {
      const base = fakeApi();
      const preflight = vi.fn(base.preflight);
      const startCampaign = vi.fn(base.startCampaign);
      const renewLease = vi.fn(async (current: Lease) => ({ ...current, generation: current.generation + 1, expires_monotonic_ns: current.expires_monotonic_ns + 30_000_000_000 }));
      const api = { ...base, preflight, startCampaign, renewLease };
      const { unmount } = renderWithRuntime(<ExpertValidationApp api={api} />, renewLease);
      await act(async () => {});
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Acquire lease" })); });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Generate points" })); });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check resources" })); });
      expect(preflight.mock.calls[0][1]).toMatchObject({ lease_generation: 1 });

      await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Start validation" })); });

      expect(startCampaign.mock.calls[0][1]).toMatchObject({ lease_generation: 2 });
      expect(preflight.mock.calls).toHaveLength(2);
      expect(preflight.mock.calls[1][1]).toMatchObject({ lease_generation: 2 });
      unmount();
      await vi.advanceTimersByTimeAsync(60_000);
      expect(renewLease).toHaveBeenCalledOnce();
    } finally {
      vi.useRealTimers();
    }
  });

  test("failed renewal disables execution and allows a fresh lease request", async () => {
    vi.useFakeTimers();
    try {
      const renewLease = async (): Promise<Lease> => { throw new Error("LEASE_EXPIRED"); };
      const api = { ...fakeApi(), renewLease };
      renderWithRuntime(<ExpertValidationApp api={api} />, renewLease);
      await act(async () => {});
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Acquire lease" })); });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Generate points" })); });
      await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });

      expect((screen.getByRole("button", { name: "Start validation" }) as HTMLButtonElement).disabled).toBe(true);
      expect((screen.getByRole("button", { name: "Acquire lease" }) as HTMLButtonElement).disabled).toBe(false);
      expect(screen.getByText(/LEASE_EXPIRED/)).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  test("newly started campaign begins watching and unmount stops it", async () => {
    const user = userEvent.setup();
    const stop = vi.fn();
    const watchCampaign = vi.fn(() => stop);
    const { unmount } = render(
      <ExpertValidationApp api={fakeApi({ watchCampaign })} />,
    );
    await user.click(await screen.findByRole("button", { name: "Acquire lease" }));
    await user.click(screen.getByRole("button", { name: "Generate points" }));
    await user.click(screen.getByRole("button", { name: "Start validation" }));

    expect(watchCampaign).toHaveBeenCalledWith("campaign-1", 1, expect.any(Function));
    unmount();
    expect(stop).toHaveBeenCalledOnce();
  });

  test("changing count invalidates generated preview", async () => {
    const user = userEvent.setup();
    render(<ExpertValidationApp api={fakeApi()} />);
    await user.click(await screen.findByRole("button", { name: "Acquire lease" }));
    await user.click(screen.getByRole("button", { name: "Generate points" }));
    const start = screen.getByRole("button", { name: "Start validation" }) as HTMLButtonElement;
    expect(start.disabled).toBe(false);
    const count = screen.getByLabelText("Final point count");
    await user.clear(count);
    await user.type(count, "12");
    expect(start.disabled).toBe(true);
  });

  test("parallel setup shows capacity admission and worker lanes", async () => {
    const user = userEvent.setup();
    const campaign = {
      campaign_id: "campaign-1", sequence: 3, execution_mode: "PARALLEL" as const,
      batch_cleanup_complete: false, points: [],
      workers: [
        { worker_id: "worker-1", generation: 1, state: "EXECUTING", lease_count: 1 },
        { worker_id: "worker-2", generation: 1, state: "EXECUTING", lease_count: 1 },
      ],
      requested: 20, evaluated: 2, execution_started: 2, valid_succeeded: 0,
      valid_failed: 0, indeterminate: 0, not_executed: 18,
      evaluation_coverage: 0.1, execution_coverage: 0.1, levels_used: [],
      fallback_history: [], infra_attempts: 0, resource_observations: {},
    };
    render(<ExpertValidationApp api={fakeApi({ restoreCampaign: async () => campaign })} />);
    await user.selectOptions(await screen.findByLabelText("Execution mode"), "PARALLEL");
    await user.selectOptions(screen.getByLabelText("Worker count"), "2");
    expect(screen.queryByLabelText("Max points per worker")).toBeNull();
    expect(screen.queryByText(/^Capacity/)).toBeNull();
    expect(screen.getByText("共享队列 · 每 worker 一次一任务")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Acquire lease" }));
    await user.click(screen.getByRole("button", { name: "Generate points" }));
    await user.click(screen.getByRole("button", { name: "Check resources" }));
    expect(await screen.findByText("Parallel admission passed")).toBeTruthy();
    expect(screen.getByLabelText("Worker worker-1")).toBeTruthy();
    expect(screen.getByLabelText("Worker worker-2")).toBeTruthy();
  });

  test("adaptive setup shows fallback timeline and observational resources", async () => {
    const user = userEvent.setup();
    const campaign = {
      campaign_id: "campaign-1", sequence: 8, execution_mode: "ADAPTIVE" as const,
      status: "RUNNING", batch_cleanup_complete: false, points: [], workers: [],
      requested: 20, evaluated: 5, execution_started: 5, valid_succeeded: 4,
      valid_failed: 0, indeterminate: 1, not_executed: 15,
      evaluation_coverage: 0.25, execution_coverage: 0.25,
      levels_used: [8, 6],
      fallback_history: [{ from_count: 8, to_count: 6, reason: "WORKER_START_FAILED" }],
      infra_attempts: 1, resource_observations: { memory_pressure: "HIGH" },
    };
    render(<ExpertValidationApp api={fakeApi({ restoreCampaign: async () => campaign })} />);
    await user.selectOptions(await screen.findByLabelText("Execution mode"), "ADAPTIVE");
    expect(screen.queryByLabelText("Max points per worker")).toBeNull();
    expect(screen.getByText("W8 -> W6 -> W4 -> W2 -> W1")).toBeTruthy();
    expect(screen.getByText("Resource observations only")).toBeTruthy();
    expect(await screen.findByText("W8 -> W6: WORKER_START_FAILED")).toBeTruthy();
  });


});


test("server capability supplies all eight options and exact twenty-point N8 K3 request", async () => {
  const user = userEvent.setup();
  const preflight = vi.fn(fakeApi().preflight);
  const original = fakeApi();
  render(<ExpertValidationApp api={fakeApi({
    capabilities: async () => ({ ...await original.capabilities(), fixed_worker_counts: [1,2,3,4,5,6,7,8] }),
    preflight,
  })} />);
  await act(async () => {});
  const workers = screen.getByRole("combobox", { name: "Worker count" }) as HTMLSelectElement;
  expect(Array.from(workers.options).map(option => option.value)).toEqual(["1","2","3","4","5","6","7","8"]);
  await user.selectOptions(screen.getByRole("combobox", { name: "Execution mode" }), "PARALLEL");
  expect(workers.options[0].disabled).toBe(true);
  expect(workers.options[0].text).toMatch(/SEQUENTIAL/);
  fireEvent.change(screen.getByRole("spinbutton", { name: "Final point count" }), { target: { value: "20" } });
  expect(screen.queryByText(/^Capacity/)).toBeNull();
  await user.selectOptions(workers, "8");
  expect(screen.getByText("NOT_MEASURED · BUDGET_PROFILE_UNAVAILABLE")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Acquire lease" }));
  await user.click(screen.getByRole("button", { name: "Generate points" }));
  await user.click(screen.getByRole("button", { name: "Check resources" }));
  expect(preflight).toHaveBeenCalledWith(expect.objectContaining({ contract_version: 3, execution_mode: "PARALLEL", worker_count: 8 }), expect.objectContaining({ lease_id: "lease-a", lease_generation: 1 }));
});

test("worker choices follow a narrower server capability without invented counts", async () => {
  const original = fakeApi();
  render(<ExpertValidationApp api={fakeApi({ capabilities: async () => ({
    ...await original.capabilities(), fixed_worker_counts: [1,2,4],
  }) })} />);
  await act(async () => {});
  const workers = screen.getByRole("combobox", { name: "Worker count" }) as HTMLSelectElement;
  expect(Array.from(workers.options).map(option => option.value)).toEqual(["1","2","4"]);
});

test("acquiring a lease presents instance authority through the runtime transport", async () => {
  const posted: string[] = [];
  const transport: DomainTransport = {
    register: async (domain) => ({ instance_id: `i-${domain}`, proof: `p-${domain}`, domain }),
    connect: async (proof) => ({ instance_id: proof.instance_id, revision: 1, domain: proof.domain }),
    snapshot: async () => ({ sequence: 0, serviceEpoch: "e1", executionGeneration: 1, payload: null }),
    subscribe: () => () => undefined,
    renew: async () => undefined,
    setAuthority: () => undefined,
    post: async (path) => {
      posted.push(path);
      return {
        lease_id: "L1",
        service_session_id: "s1",
        generation: 1,
        expires_monotonic_ns: 10 ** 15,
      };
    },
    close: () => undefined,
  };
  const runtime = new DomainRuntime("validation", transport);
  // No api prop: the page uses its own client, which is the case this test is about.
  render(
    <RuntimeProvider validation={runtime}>
      <ExpertValidationApp />
    </RuntimeProvider>,
  );
  await act(async () => {
    runtime.adoptAuthority({
      instanceId: "i-validation",
      proof: "p",
      channelRevision: 1,
      executionGeneration: 1,
    });
  });
  const acquire = await screen.findByRole("button", { name: /acquire lease/i });
  await userEvent.click(acquire);
  // The runtime transport is the only path that carries the four authority headers; the page used to
  // send its mutations through its own bare client, where they do not exist.
  await waitFor(() => expect(posted).toContain("/expert-validation/lease"));
  // Every mutation, not just the acquire: generating the manifest was refused the same way until the
  // whole mutating surface went through the runtime.
  const generate = screen.getByRole("button", { name: /generate points/i });
  await act(async () => { fireEvent.click(generate); });
  await waitFor(() => expect(posted).toContain("/expert-validation/manifests"));
});

test("a stored lease does not restore execution permission", async () => {
  // Design section 5.1: local storage restores only the read-only projection, never execution
  // permission. Renewing a stored lease on mount did exactly the opposite, and it did it through a
  // client that carries no instance authority.
  sessionStorage.setItem("so101-expert-validation-service-session", "s-stored");
  sessionStorage.setItem(
    "so101-expert-validation-lease",
    JSON.stringify({
      lease_id: "l-stored",
      service_session_id: "s-stored",
      generation: 1,
      expires_monotonic_ns: 10 ** 15,
    }),
  );
  const base = fakeApi();
  const renewLease = vi.fn(base.renewLease);
  render(<ExpertValidationApp api={{ ...base, renewLease }} />);
  await act(async () => {});
  await act(async () => {});
  expect(renewLease).not.toHaveBeenCalled();
  sessionStorage.clear();
});
