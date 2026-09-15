# SO-101 Stateless Perception Broker Design

## Status and decision

This design records the user-approved correction to the parallel validation architecture on
2026-09-15. It supersedes earlier requirements that made each inference request prove the current
Coordinator lease, Worker generation, start event, or journal state inside the perception service.

The shared perception Broker is a stateless compute service with respect to batch scheduling. A
late or duplicated inference may consume extra GPU work; that cost is acceptable for this offline
validation system. The Broker must never become an authority for point ownership or robot motion.

## Responsibility boundary

The Broker owns only:

- bounded concurrent IPC request handling;
- bounded per-model queues and configured executor counts;
- YOLO-first inference and the existing permitted Grounded-SAM fallback behavior;
- exact request-to-response correlation;
- per-request queue, inference, and end-to-end deadlines;
- model readiness, model provenance, response serialization, and operational metrics.

The Broker does not own or consult:

- Coordinator leases or Worker generations;
- batch, attempt, reset, or start-event authorization;
- Coordinator snapshots or journals;
- durable idempotency or result admission;
- robot motion permission.

Coordinator leases and journals remain confined to point scheduling, Worker lifecycle, final result
admission, recovery, and audit. A Worker or execution adapter must validate current action authority
before motion and the Coordinator must validate ownership when accepting a final point result.

## IPC contract

An inference request needs a unique in-flight `request_id`, a `model_id`, immutable input reference
or bytes, input digest where the existing transport uses one, inference options, and a caller
deadline. Scheduling fields may temporarily remain as opaque compatibility metadata, but the Broker
must neither require them nor compare them with Coordinator state.

Every response echoes the exact `request_id` and contains the model identity/version, terminal
status, result or structured error, and timing data. Concurrent requests may complete out of order;
each response must return to the originating request. Two requests for the same point or image are
valid independent work and may both run. No durable replay cache is required. An identical
`request_id` that is already in flight may be rejected locally to prevent ambiguous response
correlation; this is not a scheduling or lease decision.

The Unix socket keeps bounded framing, schema validation, filesystem permissions, connection
limits, and request deadlines. Inference requests do not call a Coordinator authentication or
authorization endpoint. Process readiness and health may remain as low-rate lifecycle control, but
must not add Coordinator or journal work to the inference request path.

## Concurrency and failure behavior

The configured connection-handler limit admits concurrent clients. Per-model executor pools bound
actual GPU work, and bounded queues provide backpressure. A full queue returns a prompt structured
busy/queue-full response. One request timing out or disconnecting does not cancel or misroute any
other request. Cancellation is best effort and local to the Broker.

A stale Worker may receive a stale inference response. That response is data only. The later motion
and final-result boundaries remain responsible for rejecting stale ownership. Broker failure is an
infrastructure result observed by the caller; it is not converted into a perception-model fallback.

## Compatibility and cleanup

Remove dead Broker-to-Coordinator inference-authority code and metrics rather than keeping two
competing paths. Do not globally weaken authenticated Coordinator/Worker control sockets that are
still used for scheduling and result commits. Preserve the default W8 admission/fallback policy and
the optional W16 ceiling; this change only simplifies the shared inference service boundary.

## Acceptance

The implementation is accepted only when:

1. A Broker can serve inference with no Coordinator inference-authority server and no journal access.
2. Ten concurrent requests under C2 complete with exact, out-of-order-safe response correlation.
3. Duplicate semantic work is accepted and recomputed; no lease or start-event field gates it.
4. Queue-full and deadline behavior are bounded and isolated per request.
5. Focused and ordinary `so101_demo_py` package tests pass from a clean `/data` scratch root.
6. A real-YOLO perception-only W10 gate passes with zero Coordinator inference calls.
7. A clean fixed-W10 execution run completes the 20-point qualification contract, or records the
   first new failure boundary without masking it by timeout, retry, fallback, or worker reduction.
8. Exact cleanup leaves no task-owned Worker, Broker, ROS, simulator, test, container, or GPU process.

