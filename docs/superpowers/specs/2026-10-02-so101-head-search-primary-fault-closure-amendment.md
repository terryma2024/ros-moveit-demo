---
status: proposed
scope: Head Search v2 primary reaction to monitor loss
base_contract: 2026-10-02-so101-head-search-feedback-freshness-amendment.md
base_sha256: 21c9941493322491e9290db10cacfd9a3ba0f5ff07d817c0325205cdeca9d891
---

# Head Search primary fault closure

## Failure boundary

The primary must close admission when its CPU-only monitor stops responding. The
monitor endpoint authenticates only the monitor process. The main primary
endpoint's normal generation close does not set the incarnation fault latch.
A live monitor with a stalled executor retains its PID/start identity, so native
peer-death detection cannot establish closure. The primary therefore needs its
own authenticated fault-close path. An intentionally rejected connection to the
monitor endpoint is not that path and cannot supply a qualifying close ACK.

This amendment replaces the ambiguous primary request for the "same strict
native closure" in revision 3 of the base contract. It adds the path below and
extends revision 4 provisioning and readiness checks to cover it. Other frame,
feedback, inference, inventory, stop, approval and qualification rules remain
binding. The base contract's bytes and approval record remain unchanged.

## Native authority and protocol

Add one Head Search v2 close-only primary fault endpoint inside the existing neck
controller process. It shares the admission gate and persistent revocation latch
with the main reservation endpoint and the monitor revocation endpoint. Its
independent listener and service thread use the same proposed 2 ms revoker
connection deadline and bounded parsing. They do not wait for either other
listener, a main incomplete frame, goal decoding or a ROS executor callback.

The new endpoint accepts only SOIA identity queries and SOGR generation-close
requests. A valid close invokes `revoke_generation()`, not `close_generation()`.
The existing reply encoding remains unchanged: the ACK names the requested
generation and proves the gate was fault-latched before reply transmission.
The query returns the same neck role, generation, incarnation and boot identity.
It does not grant arming, reservation, ingress authorization or action authority.

Authenticate exactly the primary UID/PID/start ticks, a distinct random capability,
the owned native UID/PID/start ticks, simulation session and neck-only scope.
Use a separate private provision and short socket path. Do not widen either
existing endpoint's allowed peer set or reuse its capability. The provision has
an explicitly distinct primary-fault authority code. Verify its fixed encoding,
private ownership/mode, regular-file identity, parent paths and process identities
under the existing provisioning rules. Record its digest and public identity
without recording the secret capability.

The main endpoint retains its 50 ms connection deadline, exact primary peer,
normal close, arm, reservation, raw digest and complete goal checks. The monitor
endpoint retains its exact monitor peer and close-only authority. Head Search v2
requires all three valid provisions before the native composition is available.
Missing or invalid required provisioning fails closed without publishing a main
admission endpoint. Unrelated legacy consumers do not require the new provision.

Generation validation and latch update are atomic under the shared gate guard.
A valid same-generation repeat is idempotent: it may ACK the already fault-latched
generation, but never clears a latch or changes identity. A well-formed close for
a different or zero generation returns REJECT without fault-latching another
generation. Foreign peers, malformed requests, invalid capability/scope and worker
failure follow the existing revoker fail-closed behavior. Endpoint/lifecycle
recreation retains the controller-owned latch; normal primary close or a higher
generation arm cannot reset it. A new attempt requires verified owned teardown
and a fresh controller incarnation.

## Startup and runtime ordering

Exec the CPU-only monitor before CUDA initialization. Create the main, monitor
revoker and primary fault provisions for the one owned composition. Authenticated
presence covers all three scopes and exact native/primary/monitor identities.
Complete the stopped bootstrap, freeze the proposed policy and obtain the monitor's
exact policy ACK before arming. The primary arms only through its main endpoint.

Read SOIA independently through each of the three endpoints after arming. All
replies must match the declared neck role, generation, native incarnation, boot
and owned process identity. The monitor's ARMED_READY ACK binds all three endpoint
identities and provision digests together with the policy, epoch and dependency
hashes. No UUID inventory, reservation or send is allowed before that ACK. A
failure after arming closes through an available authenticated fault endpoint
and follows the existing cancellation and owned teardown rules.

On monitor heartbeat expiry, loss of authenticated channel, process death or
identity/epoch mismatch, the primary irreversibly closes local admission before
queuing any work. It concurrently starts strict native close through its own
fault endpoint and scoped cancellation/reconciliation of every inventoried UUID.
Neither operation waits for a monitor reply, normal main close ACK or queued
reservation worker. The primary fault-close worker is independent of the main
reservation/send worker. The watchdog enqueues bounded work outside cache and
watchdog locks. The unchanged 10 ms proposed reaction bound covers guard detection,
gate-lock acquisition, fault closure and cancellation initiation. Actual measured
evidence is required; a 2 ms socket deadline alone does not establish that bound.

The primary uses its own original feedback cache, matching decision clocks and
actual port predicate to prove every acceptance/rejection/terminal state and three
strictly post-request quiet samples by the unchanged fault-to-stop deadline.
The earliest observed fault crossing sets that deadline. Recovered monitor replies,
old heartbeats and queued operations cannot reopen admission or erase the fault.
Each operation still rechecks readiness, current epoch and monitor liveness before
reservation and immediately before send. Late acceptance remains unresolved until
an authoritative rejection or terminal result is observed; quiet velocities alone
do not confirm it.

A close ACK must pass the existing strict channel/peer/status/generation/native
identity checks. Lost, malformed, late or mismatched ACKs are unconfirmed closure.
Cancellation continues, and the exact owned composition is retired if timely
closure and stop cannot be proven. Monitor retirement followed by native peer-death
detection is containment evidence; it cannot substitute for an authenticated
fault-close ACK or turn teardown into a qualifying stop. A failed monitor's missing
stream or missing timely proof produces a failed/unconfirmed run.

## Evidence, approval and controls

Seal all three endpoint/provision identities, source/install dependencies, primary
and monitor fault crossings, attempted close opcode, exact replies, cancellation
initiation, UUID reconciliation, original stop samples and observed predicate
times. Both original streams and their authenticated links remain mandatory for
qualification; monitor-loss negative controls preserve missing/failed evidence
without manufacturing a monitor response. The actual journal aggregator refuses
missing authoritative closure, terminal state or deadline proof.

The policy retains its eight quantities. `revoker_connection_deadline_s` applies
to both independently serviced close-only endpoints. This adds a policy consumer
and runtime dependency, not an approved numerical value. Fresh formal calibration
and exact human bundle approval must include that consumer, all identities,
formula populations, measured margins and the 17 values. Existing approvals
cannot be copied to this dependency graph.

Before runtime integration, obtain independent GPT-6 Astra / High review of this
exact amendment. Implementation requires genuine targeted RED/GREEN, complete
native dependency tests and independent GPT-6.1 Sol / High source review. Native
and actual runtime controls must cover:

- A live but unresponsive monitor with pending reservation/send; delayed send
  after reservation ACK; cancel-before-accept; and acceptance racing fault close.
- A genuinely incomplete main connection occupying its 50 ms worker while the
  primary's separate fault listener closes the gate and cancellation starts
  inside the proposed reaction limit.
- Wrong peer, PID reuse, capability, role, generation and opcode; no arm/reserve
  through either fault endpoint; and unchanged main normal-close sequencing.
- Both peers closing concurrently, idempotent same-generation close, stale close
  that cannot affect another generation, lost ACK and strict reply tampering.
- Monitor recovery, queued-operation recovery, higher-generation arm and lifecycle
  recreation after fault; no admission until teardown and a fresh incarnation.

Preserve each actual failure and owned teardown proof. Helper tests and native ACK
timings establish only their tested boundary. Final smoke, all 40 scenarios, the
three independent anchor restarts and real Teleop acceptance still require the
approved final installed runtime and independent final review.
