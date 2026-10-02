# Head Search reservation binding amendment

Status: approved with findings by independent GPT-6 Astra / High review of revision 1
(`3c9189def45ac7c0e353407aeadb7401ac9fdf5e558801100de12df9c3bf50c0`).
The implementation and review must close the findings below.

## Failure and scope

HS-327 reproduced a bound reservation that ACKed, followed by rejection of the same
action goal with `DENY_DIGEST_MISMATCH`. Admission closed the generation, so the next
reservation returned `DENY_CLOSED`. Its evidence is retained in
`reviews/reservation-and-joint-rate-diagnosis.md` under the registered antzb evidence
root. The serialized goal contained 28 trailing bytes the serializer did not write.
Hashing a new serialization therefore did not identify the goal. EXP-511/512 had
already established that raw CDR equality cannot identify a goal across the action hop.

This amendment changes the bound reservation implementation in
`src/so101_mujoco_support`. The Python sender, `SOGB` v2 layout, capability, wire
`target_digest = SHA256(goal_cdr)`, identity and generation fields remain unchanged.
Calibration values, model weights, camera settings and joint-feedback policy are
outside this change. It requires a fresh installed runtime and later calibration
approval and complete qualification, as required by the takeover handoff.

## Binding contract

The parser retains the exact bounded `goal_cdr` bytes in
`BoundControllerReservationRequest`, alongside the decoded `ControllerGoal`.
`reserve_bound` hashes those retained bytes and compares the result to
`target_digest`. It independently decodes the retained payload and compares the
complete decoded goal with `request.goal`. This second check prevents direct callers
from mutating the typed request after parsing while retaining its previous digest.
An empty, oversized, undecodable or inconsistent payload fails closed. No supplied
boolean or precomputed digest can bypass these checks.

The reservation stores an immutable copy of the verified typed goal. At action
admission, complete generated `FollowJointTrajectory::Goal` equality binds the
received action goal to that reservation. Equality covers both trajectory headers,
joint names, every point and duration, the multi-DOF transforms and twists,
path/goal tolerances, component tolerances, and goal-time tolerance. It does not
hash a new CDR serialization. The existing serialized-size bound still applies to
action goals; serialization used for that bound never supplies identity.

The wire digest continues to authenticate the exact bytes carried by the reservation
request. Complete typed equality carries that verified intent across the action
hop. Unwritten CDR tail or padding bytes can differ at that hop without changing
the goal; any goal field unequal under generated equality must be refused.
Generated equality treats `+0.0` and `-0.0` as equal. NaN compares unequal to itself,
so a NaN-containing request fails the independently decoded consistency check.
Tests must cover both consequences. No approximate comparison is allowed.

Decode, hash, size checks and construction of the immutable goal happen outside the
gate mutex. The mutex still protects reservation lookup, generation checks, one-use
consumption and gate closure. Storage uses an immutable shared goal so inserting
the verified reservation does not copy its variable-length fields under the mutex.
The action comparison reads that immutable goal while the reservation is protected.

## Refusal and lifecycle rules

Wire digest or typed-goal mismatch returns `DENY_DIGEST_MISMATCH` and preserves
tombstones and generation closure. Invalid serialization or size fails closed.
The existing handling of capability, role, controller incarnation, boot identity,
generation, UUID and permit replay, expiry, clock regression, cancellation,
one outstanding reservation, lifecycle revocation and stop proof remains binding.
Only the existing authenticated arm of a strictly newer generation can reopen a
closed gate. No retry or mismatch tolerance is introduced.

## Implementation and evidence gates

1. Capture genuine RED using the retained HS-327 neck goal through the production
   parser and `ControllerGoalAdmission`: reservation ACK followed by rejected action
   admission. Include heap disturbance and changed trailing CDR bytes to separate
   typed intent from allocator state. A compile/import failure does not count.
2. Before changing production code, add behavioral tests for the exact positive
   chain, independently varied goal fields, wire-byte/digest tampering and mutation
   of the typed request after parsing. Keep the existing identity, generation,
   replay, expiry, clock, cancellation and lifecycle tests.
3. Implement the retained-payload check and immutable typed reservation only.
   Exercise headers and all scalar/sequence fields, including multi-DOF and
   component tolerances, through both reservation consistency and action admission.
   Negative controls verify the later call sees `DENY_CLOSED`. Each replay and field
   mutation uses a separate fresh gate and asserts its first specific refusal.
   After successful reservation, mutate or destroy caller-owned goal and payload
   storage and prove the original action still succeeds. Separately prove a changed
   action fails. Test changed payload with an old digest, changed semantic payload
   with matching digest but stale typed goal, a consistent newly bound goal, invalid
   payloads, both payload size limits and oversized actions. The immutable stored
   goal must own its storage independently of the request.
4. Record argv, exit codes, timing and test/JUnit evidence under fresh task scratch.
   Rebuild the affected native package against verified dependencies. Obtain an
   independent read-only GPT-6.1 Sol / High review of the exact diff before runtime.
5. Run the actual owned production smoke from the rebuilt install. Read its sealed
   journal and aggregator output. If the separately identified joint-freshness or
   search deadline boundary prevents lock, report that exact refusal and preserve
   the reservation acceptance evidence; do not mark this task complete prematurely.

Final acceptance still requires all ordinary/package/native gates, a new formal
calibration bundle with exact human approval, one frozen installed runtime, the
40 scenarios, one independent restart per anchor, readback and real Teleop
acceptance. This amendment grants no ACT Task8 readiness or hardware authority.
