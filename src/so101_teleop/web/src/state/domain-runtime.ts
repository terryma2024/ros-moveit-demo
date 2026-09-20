/**
 * One domain's root runtime.
 *
 * The runtime owns the instance binding, the subscription and the recovery rules. It lives
 * for the whole app: switching pages must not drop a subscription, release a lease or stop a
 * renewal. Events only update the view — a sequence gap, a reconnect or an epoch change
 * fetches an authoritative snapshot and never replays a mutation.
 */
import type { TelemetrySnapshot } from "@/api/types";
import type { CampaignProjection } from "@/api/expert-validation-types";
import type { ChannelBinding, ControllerAuthority, DomainName, InstanceProof } from "@/api/instance-client";

/** The lease identity a domain holds. Mirrors the server's `LeaseIdentity` field for field. */
export type LeaseIdentity = {
  lease_id: string;
  service_session_id: string;
  generation: number;
  expires_monotonic_ns?: number;
};

export type RuntimeSnapshot = {
  sequence: number;
  serviceEpoch: string;
  executionGeneration: number;
  payload: TelemetrySnapshot | CampaignProjection | null;
};

export type DomainTransport = {
  register(domain: DomainName): Promise<InstanceProof>;
  connect(proof: InstanceProof): Promise<ChannelBinding>;
  snapshot(): Promise<RuntimeSnapshot>;
  subscribe(handler: (snapshot: RuntimeSnapshot) => void): () => void;
  /** Optional: tell the transport which authority to present on renewal. */
  setAuthority?(authority: ControllerAuthority | null): void;
  renew(): Promise<Partial<LeaseIdentity> | void>;
  post(path: string, body: Record<string, unknown>, authority: ControllerAuthority): Promise<unknown>;
  close(): void;
};

/** Events buffered while an authoritative snapshot is in flight; bounded on purpose. */
export const MAX_BUFFERED_EVENTS = 64;

export class DomainRuntime {
  private current: RuntimeSnapshot | null = null;
  private binding: ChannelBinding | null = null;
  private proof: InstanceProof | null = null;
  private authorityValue: ControllerAuthority | null = null;
  private unsubscribe: (() => void) | null = null;
  private pending: RuntimeSnapshot[] = [];
  private fetching = false;
  private disposed = false;
  private heartbeat: ReturnType<typeof setTimeout> | null = null;
  private leaseValue: LeaseIdentity | null = null;
  private readonly renewalListeners = new Set<(outcome: { ok: boolean; error: string | null }) => void>();

  constructor(
    readonly domain: DomainName,
    private readonly transport: DomainTransport,
  ) {}

  /** Read-only registration and subscription. It never acquires control. */
  async start(): Promise<void> {
    this.proof = await this.transport.register(this.domain);
    this.binding = await this.transport.connect(this.proof);
    this.authorityValue = {
      instanceId: this.binding.instance_id,
      proof: this.proof.proof,
      channelRevision: this.binding.revision,
      executionGeneration: 0,
    };
    this.current = await this.transport.snapshot();
    this.unsubscribe = this.transport.subscribe((event) => {
      void this.accept(event);
    });
  }

  /**
   * Adopt the domain lease this document holds.
   *
   * The lease identity belongs to the runtime so a renewal can be validated against it without any
   * page owning that check.
   */
  adoptLease(lease: LeaseIdentity | null): void {
    this.leaseValue = lease;
  }

  lease(): LeaseIdentity | null {
    return this.leaseValue;
  }

  /**
   * Validate a renewal against the lease this document holds.
   *
   * A renewal that changes the lease id or session, or that does not strictly increase the
   * generation, is refused: the runtime drops its lease state and records why, so the caller cannot
   * keep operating on an identity the server did not confirm.
   */
  validateRenewal(next: LeaseIdentity): boolean {
    const current = this.leaseValue;
    if (!current) {
      this.lastRenewalError = "LEASE_NOT_HELD";
      return false;
    }
    if (next.lease_id !== current.lease_id || next.service_session_id !== current.service_session_id) {
      this.lastRenewalError = "LEASE_IDENTITY_MISMATCH";
      this.leaseValue = null;
      return false;
    }
    if (next.generation <= current.generation) {
      this.lastRenewalError = "STALE_LEASE_GENERATION";
      this.leaseValue = null;
      return false;
    }
    if (
      current.expires_monotonic_ns !== undefined &&
      next.expires_monotonic_ns !== undefined &&
      next.expires_monotonic_ns <= current.expires_monotonic_ns
    ) {
      this.lastRenewalError = "LEASE_EXPIRY_NOT_EXTENDED";
      this.leaseValue = null;
      return false;
    }
    this.leaseValue = next;
    this.lastRenewalError = null;
    return true;
  }

  /**
   * Observe renewal outcomes.
   *
   * The runtime owns the renewal loop, so presentation code (notices, an indicator) subscribes here
   * instead of scheduling its own timer. Listeners are told whether the lease was accepted and, when
   * it was not, the recorded reason.
   */
  onRenewal(listener: (outcome: { ok: boolean; error: string | null }) => void): () => void {
    this.renewalListeners.add(listener);
    return () => this.renewalListeners.delete(listener);
  }

  /** Adopt the authority the server returned when control was explicitly acquired. */
  adoptAuthority(authority: ControllerAuthority): void {
    this.authorityValue = authority;
    this.transport.setAuthority?.(authority);
  }

  mutationHeaders(): ControllerAuthority | null {
    return this.authorityValue;
  }

  projection(): RuntimeSnapshot | null {
    return this.current;
  }

  async accept(event: RuntimeSnapshot): Promise<void> {
    if (this.disposed) return;
    if (this.fetching) {
      this.buffer(event);
      return;
    }
    const current = this.current;
    if (!current || event.serviceEpoch !== current.serviceEpoch || event.sequence > current.sequence + 1) {
      await this.resnapshot();
      return;
    }
    if (event.sequence <= current.sequence) return;
    this.current = event;
    this.drain();
  }

  private buffer(event: RuntimeSnapshot): void {
    if (this.pending.length >= MAX_BUFFERED_EVENTS) {
      // A bounded buffer that cannot close the sequence must resynchronise, not grow.
      this.pending = [event];
      void this.resnapshot();
      return;
    }
    this.pending.push(event);
  }

  private async resnapshot(): Promise<void> {
    this.fetching = true;
    try {
      this.current = await this.transport.snapshot();
    } finally {
      this.fetching = false;
    }
    this.drain();
  }

  private drain(): void {
    const queued = this.pending;
    this.pending = [];
    for (const event of queued) {
      const current = this.current;
      if (!current) continue;
      if (event.serviceEpoch === current.serviceEpoch && event.sequence === current.sequence + 1) {
        this.current = event;
      }
    }
  }

  /**
   * Start the lease renewal heartbeat.
   *
   * It belongs to the runtime, not to a page: switching pages must not stop a renewal, and only an
   * explicit `dispose` (the root provider unmounting) ends it. Renewal never takes the ordinary
   * mutation path, so a long arm action cannot starve it.
   */
  startHeartbeat(intervalMs: number | (() => number)): void {
    if (this.disposed || this.heartbeat !== null) return;
    const schedule = () => {
      if (this.disposed) return;
      const delay = typeof intervalMs === "function" ? intervalMs() : intervalMs;
      if (!Number.isFinite(delay) || delay <= 0) {
        // Capability-derived cadences can be invalid; refusing is safer than renewing on a guess.
        this.lastRenewalError = "LEASE_CAPABILITIES_INVALID";
        this.heartbeat = null;
        return;
      }
      this.heartbeat = setTimeout(() => {
        void this.renew()
          .catch((error: unknown) => {
            this.lastRenewalError = String(error);
          })
          .finally(() => {
            if (!this.disposed) schedule();
          });
      }, delay);
    };
    schedule();
  }

  stopHeartbeat(): void {
    if (this.heartbeat !== null) {
      clearTimeout(this.heartbeat);
      this.heartbeat = null;
    }
  }

  heartbeatRunning(): boolean {
    return this.heartbeat !== null;
  }

  lastRenewalError: string | null = null;

  /**
   * True while a renewal is in flight. The page uses this for its "renewing" indicator, which is
   * presentation state the runtime can own without the page scheduling anything.
   */
  renewing = false;

  async renew(): Promise<void> {
    if (this.disposed || !this.authorityValue) return;
    this.renewing = true;
    try {
      const next = await this.transport.renew();
      if (next && typeof next === "object" && typeof next.lease_id === "string") {
        // A renewed lease must extend the identity this document already holds; otherwise the
        // renewal is refused and the lease state dropped rather than silently accepted.
        if (!this.validateRenewal(next as LeaseIdentity)) {
          throw new Error(this.lastRenewalError ?? "LEASE_RENEWAL_INVALID");
        }
      }
    } catch (error) {
      this.lastRenewalError = String(error);
      throw error;
    } finally {
      this.renewing = false;
      const outcome = { ok: this.lastRenewalError === null, error: this.lastRenewalError };
      for (const listener of this.renewalListeners) listener(outcome);
    }
  }

  async post(path: string, body: Record<string, unknown>): Promise<unknown> {
    if (!this.authorityValue) {
      throw new Error("CONTROLLER_INSTANCE_REQUIRED: this document holds no authority");
    }
    // A timeout or a lost connection is never retried with a new command id: the caller must
    // query the recorded command instead.
    return await this.transport.post(path, body, this.authorityValue);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.stopHeartbeat();
    this.unsubscribe?.();
    this.unsubscribe = null;
    this.transport.close();
  }
}
