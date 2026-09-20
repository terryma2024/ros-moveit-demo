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
  renew(): Promise<void>;
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

  /** Adopt the authority the server returned when control was explicitly acquired. */
  adoptAuthority(authority: ControllerAuthority): void {
    this.authorityValue = authority;
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

  async renew(): Promise<void> {
    if (this.disposed || !this.authorityValue) return;
    await this.transport.renew();
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
    this.unsubscribe?.();
    this.unsubscribe = null;
    this.transport.close();
  }
}
