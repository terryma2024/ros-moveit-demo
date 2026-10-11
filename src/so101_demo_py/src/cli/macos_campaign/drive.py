"""Run the routed campaign."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sys
import time

from so101_demo.cli.macos_campaign.admission import (
    _inventory,
    _model_factories,
    admission_decision,
    build_parser,
    serve_and_admit,
    served_admission_split,
)
from so101_demo.cli.macos_campaign.guard import RefusedRun, _guard_admission, route_spec
from so101_demo.cli.macos_campaign.journal import (
    _WORKER_MODULE,
    MPS_TWO_WORKER_FIRST_PASS,
    bind_worker_requests,
    commit_campaign_terminal,
    lease_worker_execution,
    open_campaign_journal,
    summarize_per_slot_pick_place,
)
from so101_demo.cli.macos_campaign.selection import (
    bind_campaign_selection,
    campaign_verdict,
    reconcile_station,
)
from so101_demo.parallel_batch import point_drain
from so101_demo.parallel_batch.campaign_supervisor import CampaignSupervisor
from so101_demo.parallel_batch.contracts import (
    ContractError,
    resolve_execution_route,
)
from so101_demo.parallel_batch.inference_registry import InferenceRegistry
from so101_demo.parallel_batch.macos_two_worker_campaign import (
    CampaignPorts,
    MacosTwoWorkerCampaign,
)
from so101_demo.parallel_batch.start_guard_probe import (
    GuardHandoverRefused,
    compose_darwin_start_guard,
)
from so101_demo.parallel_batch.two_worker_composition import (
    CompositionError,
    load_execution_config_for_schema,
)
from so101_demo.runtime.unix_address import DarwinPrivatePathUnixAddress


def run_routed(*, argv, arguments, execution_profile: str) -> int:
    """Load the document, resolve the closed route, compose the plan and drive the campaign.

    The routing key is `(schema_version, execution_profile, batch_kind, worker_count)`. The profile
    comes from the entry point, the batch kind from the profile it names, the schema and the
    worker count from the document - and a profile is never inferred from how many points were
    selected.
    """

    spec = route_spec(execution_profile)
    document: dict = {"status": "PENDING", "execution_profile": spec.execution_profile}
    try:
        config = load_execution_config_for_schema(arguments.config)
        if not isinstance(config, spec.config_class):
            raise RefusedRun(
                "config",
                "CONFIG_SCHEMA_MISMATCH: "
                f"{execution_profile} requires {spec.config_class.__name__}, "
                f"not {type(config).__name__}")
        route = resolve_execution_route(
            schema_version=config.schema_version, execution_profile=spec.execution_profile,
            batch_kind=spec.batch_kind, worker_count=config.worker_count)
        plan = spec.composer(
            config=config, config_path=arguments.config, campaign_id=arguments.campaign_id,
            batch_id=arguments.batch_id,
            selected_point_ids=tuple(arguments.point_id) or spec.default_point_ids,
            evidence_root=arguments.evidence_root)
    except RefusedRun:
        raise
    except (ContractError, CompositionError) as error:
        raise RefusedRun("config", str(error)) from error

    document["route"] = {
        "schema_version": route.schema_version,
        "execution_profile": str(route.execution_profile),
        "batch_kind": str(route.batch_kind),
        "worker_count": route.worker_count,
        "module": spec.module,
        "config_path": str(arguments.config),
        "config_sha256": plan.config_sha256,
    }
    inventory = _inventory(arguments.campaign_id, arguments.evidence_root)
    document["inventory"] = inventory
    if not inventory["clean"]:
        raise RefusedRun(
            "inventory",
            "a claim, endpoint or campaign directory is already present; "
            "this run will not clean up someone else's resources",
            exit_code=2)
    document["plan"] = plan.to_document()
    if arguments.skip_models:
        document.update(status="COMPOSED_ONLY", stage="compose",
                        detail="--skip-models was set, so this is never a pass")
        print(json.dumps(document, indent=2, sort_keys=True))
        return 3
    return _drive_campaign(arguments, argv, plan, spec, document)


def _drive_campaign(arguments, argv, plan, spec, document) -> int:
    """Run one composed campaign: guard, broker, Workers, admission, exact cleanup."""

    supervisor = CampaignSupervisor(
        arguments.campaign_id, state_root=arguments.evidence_root / "supervisor",
        ack_timeout_s=120.0,
        # Every Worker takes its own fresh admission once its spawn intent is durable and before
        # `Popen`; the scope binds this process's real owner identity and the plan's worker count.
        spawn_guard=compose_darwin_start_guard(
            plan.config.start_guard,
            state_root=arguments.evidence_root / "start-guard-state"),
        guard_worker_count=plan.worker_count)
    address = DarwinPrivatePathUnixAddress()
    ports = CampaignPorts(model_factories=_model_factories(
        yolo_weights=arguments.yolo_weights.resolve(),
        grounded_root=arguments.grounded_root.resolve()))
    registry = InferenceRegistry(campaign_id=arguments.campaign_id)
    campaign = MacosTwoWorkerCampaign(plan=plan, address=address, supervisor=supervisor, ports=ports,
                               registry=registry)
    # The immutable selection and the durable queue exist before the first process does. A
    # selection the binding contract refuses - fewer than four points, a missing anchor, an unknown
    # id, a retry of a point that is not a committed business FAILED - stops the campaign here.
    selection, queue, catalog_path = bind_campaign_selection(
        arguments=arguments, plan=plan, spec=spec)
    campaign.bind_selection(binding=selection, queue=queue)
    selection_path = (Path(arguments.evidence_root)
                      / point_drain.SELECTION_DOCUMENT_BASENAME)
    # The campaign document states the same selection the immutable document on disk holds, from
    # that document rather than from a second projection: a retry's original chain and how it was
    # verified (`original_result_source`) therefore read the same in both places.
    written_selection = point_drain.read_selection_document(selection_path)
    document["selection"] = {
        **{key: written_selection[key] for key in (
            "kind", "selection_sha256", "catalog_sha256", "config_sha256",
            "runtime_closure_sha256", "selected_point_ids", "original_selection_sha256",
            "original_result_sha256", "original_outcome", "original_result_source",
            "original_batch_id") if key in written_selection},
        "document_path": str(selection_path),
    }
    document["queue"] = {"root": str(queue.state_path.parent),
                         "state_path": str(queue.state_path),
                         "selected_point_ids": list(selection.selected_point_ids)}

    try:
        admitted = _guard_admission(arguments, argv, plan, spec, document)
    except GuardHandoverRefused as refusal:
        document.update(status="REFUSED", stage="start_guard_handover",
                        refusal=refusal.reason, detail=refusal.detail)
        print(json.dumps(document, indent=2, sort_keys=True))
        return 4
    if admitted is None:
        return 4

    # The broker phase proper. The guard phase ran in a previous interpreter state, so torch is
    # still unimported here, which is what the bootstrap checks.
    import numpy as np

    from so101_demo.core.detection import DetectionFrame, DetectionQuery
    from so101_demo.runtime.mps_broker_bootstrap import MpsBrokerBootstrap
    from so101_demo.runtime.parallel_ipc_darwin import DarwinPermissionOnlyServer

    journal = None
    supervisor.acquire_claim()
    supervisor.note_heartbeat(owner_pid=os.getpid())
    bootstrap = None
    campaign_root = None
    campaign_root_cleaned = False
    try:
        bootstrap = MpsBrokerBootstrap(
            models=tuple(ports.model_factories.items()),
            memory_fraction=plan.mps_process_memory_fraction,
            lane_capacity=8)
        _torch, ready = bootstrap.prepare()
        document["broker"] = {
            "pid": ready.broker_pid, "birth_identity": ready.broker_birth_identity,
            "ready": ready.ready, "device": ready.runtime_device,
            "fallback_env": ready.fallback_env,
            "models": [model.model_id for model in ready.models],
            "model_devices": [model.device for model in ready.models],
            "model_parameter_devices": [list(model.parameter_devices) for model in ready.models],
            "lane_stats": dict(ready.lane_stats),
            "warmup_total_latency_s": ready.warmup_total_latency_s,
            "receipt_path": str(ready.write(arguments.evidence_root / "broker-ready.json")),
        }
        # --- the composed campaign runs: endpoint, Workers, one-time admission -------------
        campaign_root = address.create_campaign_root()
        document["campaign_root"] = str(campaign_root.campaign_path)
        journal = open_campaign_journal(
            evidence_root=arguments.evidence_root,
            campaign_id=plan.campaign_id, batch_id=arguments.batch_id)
        document["journal"] = {
            "batch_id": arguments.batch_id,
            "segment": str(journal.segment_path),
            "watermark": journal.read_watermark().as_document(arguments.batch_id)
            if journal.read_watermark() else None,
        }
        models = bootstrap.loaded_models
        served: list[dict] = []

        def warm_frame() -> DetectionFrame:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[200:280, 260:380] = 200
            return DetectionFrame(rgb8=np.ascontiguousarray(frame),
                                  source_stamp_ns=time.monotonic_ns(),
                                  source_frame_id="campaign-frame")

        # The Coordinator's table is the admission gate, so every request a Worker will make is
        # bound here *before* it is served. An id that was never bound is refused. Each lease binds
        # the single point that Worker may execute, so the table itself carries the selected-only
        # property: a point the queue never leased has no bound request either.
        import hashlib

        input_digest = hashlib.sha256(b"campaign-warm-frame").hexdigest()
        admission_deadline_s = float(getattr(plan.config, "batch_hard_timeout_s", 5400.0))
        leases: dict[str, dict] = {}

        consumed_ids: set[str] = set()
        cancelled_ids: set[str] = set()
        infer_served = 0
        handler_errors: list[dict] = []
        fault_trace: list[dict] = []

        def handler(request):
            """Serve one request: a real forward pass, admitted through the one-time table."""

            serialized_request = None
            try:
                payload = request.payload
                if isinstance(payload, (bytes, bytearray, str)):
                    payload = json.loads(payload)
                serialized_request = (payload or {}).get("request")
            except Exception:  # noqa: BLE001 - an unreadable payload is a mismatch, not a pass
                serialized_request = None
            if (arguments.cancel_second_worker_after_served
                    and len(served) == arguments.cancel_second_worker_after_served
                    and len(spec.worker_ids) > 1):
                leases_last = leases.get(spec.worker_ids[-1]) or {}
                cancelled_ids.update(f"{attempt}-{leases_last.get('model_id', 'yolo')}"
                                     for attempt in leases_last.get("attempt_ids", []))
            refusal = admission_decision(
                operation=request.operation, request_id=request.request_id,
                serialized_request=serialized_request, consumed_ids=consumed_ids,
                bound_digest=input_digest, cancelled_ids=cancelled_ids)
            if refusal is not None:
                if refusal["error"]["code"] == "DUPLICATE_REQUEST":
                    served.append({"request_id": request.request_id,
                                   "operation": request.operation, "duplicate": True})
                return refusal
            consumed_ids.add(request.request_id)

            detector = models["yolo"]
            batch = bootstrap.lane.submit(
                lambda: detector.detect(warm_frame(), DetectionQuery(class_id="cup")),
                label=f"serve:{request.operation}")
            candidates = len(getattr(batch, "candidates", ()))
            device = detector.runtime_device
            refusal = serve_and_admit(
                campaign, request_id=request.request_id, candidates=candidates, device=device,
                served=served, broker_pid=ready.broker_pid,
                broker_birth_identity=ready.broker_birth_identity)
            if refusal is not None:
                return refusal
            # Fault injection, explicit and one-shot: the Broker child is signalled by exact PID
            # only after the requested number of requests has been served, and what the campaign
            # does next is the evidence - never an automatic kill and never a silent retry.
            if (arguments.crash_broker_after_served
                    and len(served) == arguments.crash_broker_after_served
                    and not document.get("broker_crash")):
                killed = False
                if int(ready.broker_pid) == os.getpid():
                    # Fail closed rather than commit suicide: in this composition the MPS Broker is
                    # in-process, so signalling ourselves would destroy the evidence.
                    document["broker_crash"] = {"pid": ready.broker_pid,
                                                "refused": "BROKER_IS_THIS_PROCESS"}
                    return {"error": {"code": "BROKER_IS_THIS_PROCESS",
                                      "detail": request.request_id}}
                try:
                    os.kill(ready.broker_pid, signal.SIGKILL)
                    killed = True
                except OSError as error:
                    document["broker_crash"] = {"pid": ready.broker_pid, "error": str(error)}
                else:
                    document["broker_crash"] = {"pid": ready.broker_pid, "signal": "SIGKILL"}
                document["broker_crash"]["killed"] = killed
            if request.operation == "broker.infer":
                payload = request.payload or {}
                serialized = payload.get("request")
                if not isinstance(serialized, (str, bytes, dict)):
                    return {"error": {"code": "INVALID_REQUEST",
                                      "detail": request.request_id}}
                return {"ok": True, "request_id": request.request_id, "device": device,
                        "candidates": candidates}
            return {"request_id": request.request_id, "device": device,
                    "candidates": candidates}

        server = DarwinPermissionOnlyServer(
            endpoint_path=address.endpoint_path(campaign_root, "broker"), handler=handler)
        endpoint = server.start(
            address=address, root=campaign_root, role="broker", owner_pid=os.getpid(),
            owner_birth_identity=ready.broker_birth_identity)
        document["endpoint"] = {"path": str(endpoint.path),
                                "mode": oct(os.stat(endpoint.path).st_mode & 0o777)}
        document["campaign_root"] = str(getattr(campaign_root, "campaign_path", campaign_root))
        broker_pid = getattr(ready, "broker_pid", None)
        document["broker_identity"] = {
            "pid": broker_pid,
            "birth_identity": getattr(ready, "broker_birth_identity", None),
            "in_campaign_process": broker_pid == os.getpid(),
        }

        # --- the drain: one lease, one point, one commit; then the next lease ---------------
        slot_index = {slot_id: index for index, slot_id in enumerate(plan.slots.slot_ids)}

        def lease_point(worker_id: str, slot_id: str, generation: int) -> dict:
            """Lease the queue's next point and write the document this Worker executes from."""

            lease_document = lease_worker_execution(
                queue=queue, binding=selection, worker_id=worker_id, slot_id=slot_id,
                evidence_root=arguments.evidence_root, input_sha256=input_digest,
                deadline_s=arguments.worker_deadline_s, generation=generation,
                execution_profile=spec.execution_profile, batch_kind=spec.batch_kind,
                schema_version=getattr(plan, "schema_version", None),
                tamper_input_sha256=arguments.tamper_snapshot_sha,
                duplicate_probe=arguments.duplicate_probe,
                lease_name=f"{worker_id}-lease-{int(generation):02d}.json", journal=journal)
            leases[worker_id] = lease_document
            bind_worker_requests(campaign, {worker_id: lease_document}, ready=ready,
                                 deadline_s=admission_deadline_s)
            return lease_document

        def spawn_worker(worker_id: str, slot_id: str, generation: int,
                         lease_document: dict) -> point_drain.WorkerRun:
            """Spawn one Worker for exactly this lease, with its own fresh start-guard admission."""

            slot = slot_index[slot_id]
            attempt_id = str(lease_document["attempt_id"])
            # Every lease gets its own ack, result and station root: a later point can never
            # overwrite the evidence of an earlier one, and a station is never reused.
            ack = arguments.evidence_root / f"{worker_id}-ack-{attempt_id}.json"
            result_path = arguments.evidence_root / f"{worker_id}-result-{attempt_id}.json"
            station_root = point_drain.station_root_for(
                evidence_root=arguments.evidence_root, worker_id=worker_id, attempt_id=attempt_id)
            station_root.mkdir(parents=True, exist_ok=True)
            record = supervisor.spawn(
                role="worker", slot=slot,
                argv=[sys.executable, "-m", _WORKER_MODULE, str(ack), str(endpoint.path),
                      worker_id, str(result_path),
                      f"{arguments.campaign_id}-{worker_id}-{attempt_id}",
                      str(station_root), str(plan.ros_domain_ids[slot]),
                      str(lease_document["lease_path"])],
                nonce=f"{arguments.campaign_id}-{worker_id}-{attempt_id}", ack_path=ack,
                ack_timeout_s=120.0)
            journal.append_committed(
                "WORKER_REGISTERED", f"{arguments.batch_id}/WORKER_REGISTERED/{attempt_id}",
                {"worker_id": worker_id, "slot_id": slot_id, "generation": generation,
                 "point_id": lease_document["point_id"], "attempt_id": attempt_id,
                 "pid": record.pid, "birth_identity": record.birth_identity,
                 "status": record.status})
            return point_drain.WorkerRun(
                worker_id=worker_id, slot_id=slot_id, generation=generation, pid=record.pid,
                status=record.status, result_path=result_path, station_root=str(station_root))

        def release_worker(worker_id: str, slot_id: str) -> str:
            """Wait for this attempt's Worker to exit, then free its slot for the next lease.

            The bound is the station-teardown scale, not the batch budget: a Worker whose result is
            already durable must not hold the slot for the whole campaign while it shuts its
            station down. One that outlives this bound is stopped by its exact identity.
            """

            return supervisor.release_child(
                role="worker", slot=slot_index[slot_id],
                wait_s=float(getattr(plan.config, "executing_hard_timeout_s", 180.0)))

        report = point_drain.drain_point_queue(
            queue=queue, binding=selection, worker_ids=spec.worker_ids,
            slot_ids=plan.slots.slot_ids, evidence_root=arguments.evidence_root,
            lease_point=lease_point, spawn_worker=spawn_worker, release_worker=release_worker,
            station_readback=lambda station_root: reconcile_station(station_root),
            # A Worker that exits without a result document is an infrastructure failure, not a
            # reason for the campaign to wait out its whole budget.
            worker_alive=lambda run: not supervisor.is_gone(run.pid) if run.pid else True,
            journal=journal,
            wait_timeout_s=float(getattr(plan.config, "batch_hard_timeout_s", 5400.0)) + 600.0)
        workers = [dict(spawn) for spawn in report.spawns]
        document["workers"] = workers
        document["drain"] = {"stop_reason": report.stop_reason,
                             "stop_detail": report.stop_detail,
                             "stopped_at_cap": report.stopped_at_cap,
                             "releases": [dict(release) for release in report.releases]}
        points_summary = report.summary(selected_point_ids=selection.selected_point_ids)
        document["points"] = points_summary
        # The result documents are re-read from disk as evidence rather than restated from memory.
        results: list[dict] = []
        for spawn in workers:
            path = Path(str(spawn["result_path"]))
            try:
                results.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                results.append({"worker_id": spawn["worker_id"], "unreadable": str(path)})
        document["worker_results"] = results

        # Evidence must not be sealed while handlers are still in flight.
        server.join_workers(timeout_s=30.0)   # returns None; the wait itself is the guarantee
        document["handlers_joined"] = True
        document["server_rejections"] = list(getattr(server, "rejections", ()) or ())
        document["fault_trace"] = fault_trace
        document["cancelled_ids"] = sorted(cancelled_ids)

        per_slot = summarize_per_slot_pick_place(evidence_root=arguments.evidence_root,
                                                 workers=spec.worker_ids)
        document["per_slot_pick_place"] = per_slot
        document["handler_errors"] = handler_errors

        # Every response was admitted through the one-time table when it was served.
        admitted_responses, refused = served_admission_split(served)
        document["admission"] = {"admitted": admitted_responses, "refused": refused}
        document["served"] = {
            "count": len(served),
            "devices": sorted({item["device"] for item in served if "device" in item}),
            "duplicates_refused": sum(1 for item in served if item.get("duplicate")),
            "lane_stats": {"executed": bootstrap.lane.stats.executed,
                           "max_concurrent": bootstrap.lane.stats.max_concurrent,
                           "rejected": bootstrap.lane.stats.rejected},
        }

        server.stop()
        cleanup = address.cleanup_campaign(campaign_root)
        campaign_root_cleaned = bool(cleanup.complete)
        document["cleanup"] = {
            "complete": cleanup.complete, "directory_removed": cleanup.directory_removed,
            "registry_empty": address.registry == (),
        }
        supervisor.terminate_all()
        document["cleanup"]["workers_reaped"] = [supervisor.is_gone(w["pid"]) for w in workers]
        # Every station this campaign started, read back and - if a killed Worker left one behind -
        # stopped by exact identity. A station that outlives the campaign is residue, and residue is
        # never a pass.
        station_roots = sorted({str(spawn["station_root"]) for spawn in workers
                                if spawn.get("station_root")})
        stations = [reconcile_station(root) for root in station_roots]
        document["cleanup"]["stations"] = stations
        document["cleanup"]["stations_clear"] = all(item["clear"] for item in stations)
        document["cleanup"]["complete"] = bool(
            document["cleanup"]["complete"] and document["cleanup"]["stations_clear"])

        document["status"] = campaign_verdict(
            spec=spec, cleanup_complete=bool(document["cleanup"]["complete"]), results=results,
            workers=workers, served=document["served"], refused=refused,
            points=points_summary)
        # The terminal events are committed before the document is sealed, so the recorded
        # watermark covers every canonical event of the run. The `finally` block repeats them
        # defensively; a repeated idempotency key returns the original event and cannot move the
        # watermark backwards.
        commit_campaign_terminal(
            journal, outcome=str(document["status"]),
            cleanup_complete=bool(document["cleanup"]["complete"]))
        document["journal"] = {**document["journal"], "terminal_watermark": (
            journal.read_watermark().as_document(arguments.batch_id)
            if journal.read_watermark() else None)}
        document["journal_terminal"] = True
        print(json.dumps(document, indent=2, sort_keys=True))
        (arguments.evidence_root / "campaign-result.json").write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n")
        return 0 if document["status"] == spec.pass_label else 7
    finally:
        supervisor.terminate_all()
        if campaign_root is not None and not campaign_root_cleaned:
            # A campaign that aborts before its cleanup phase must not leave a registered endpoint
            # behind: `read_inventory` treats a live campaign directory as someone else's resource
            # and would refuse the next campaign on this host. Best effort, reported by the caller.
            try:
                address.cleanup_campaign(campaign_root)
            except Exception:  # noqa: BLE001 - the residue readback is what reports this
                pass
        if journal is not None:
            try:
                commit_campaign_terminal(
                    journal, outcome=str(document.get("status", "UNKNOWN")),
                    cleanup_complete=bool(document.get("cleanup", {}).get("complete")))
                document["journal_terminal"] = True
                (arguments.evidence_root / "campaign-result.json").write_text(
                    json.dumps(document, indent=2, sort_keys=True) + "\n")
            finally:
                journal.close()
        supervisor.release_claim()
        if bootstrap is not None:
            bootstrap.lane.shutdown()


def run(argv: list[str] | None = None) -> int:
    """The v4 exact two-worker entry point. The profile is this module's; it is not a flag."""

    arguments = build_parser().parse_args(argv)
    arguments_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        return run_routed(argv=arguments_argv, arguments=arguments,
                          execution_profile=MPS_TWO_WORKER_FIRST_PASS)
    except RefusedRun as refusal:
        print(json.dumps({"status": "REFUSED", "stage": refusal.stage, "detail": refusal.detail},
                         indent=2, sort_keys=True))
        return refusal.exit_code
