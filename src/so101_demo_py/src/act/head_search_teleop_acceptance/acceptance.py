"""The teleop acceptance run and its entry point."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import signal
import time

from so101_demo.act.head_search_teleop_acceptance.receipts import (
    APP_START_TIMEOUT_S,
    APP_STOP_TIMEOUT_S,
    CLEANUP_ARTIFACT,
    CONNECTION_ARTIFACT,
    DEFAULT_FRAME_PROBE,
    DEFAULT_WEB_PORT,
    E2E_COMMAND,
    FAILED,
    HEAD_CAMERA_IMAGE_TOPIC,
    OPERATION,
    PASSED,
    PROFILE,
    RECEIPT_ARTIFACT,
    REFUSED,
    SOCKET_PATH_LIMIT_BYTES,
    STATE_ARTIFACT,
    STOP_SAMPLES,
    TEARDOWN_ARTIFACT,
    TELEOP_APP_NOT_SERVED,
    TELEOP_BUNDLE_MISMATCH,
    TELEOP_DETECTOR_FAILED,
    TELEOP_E2E_EVIDENCE_MISSING,
    TELEOP_E2E_FAILED,
    TELEOP_FRAME_PROBE_FAILED,
    TELEOP_GPU_NOT_RELEASED,
    TELEOP_INPUTS_INCOMPLETE,
    TELEOP_OWNERSHIP_REFUSED,
    TELEOP_PROBE_FAILED,
    TELEOP_REPORT_NOT_CLOSED,
    TELEOP_REPORT_NOT_PUBLISHED,
    TELEOP_RUN_ROOT_EXISTS,
    TELEOP_RUNTIME_UNVERIFIED,
    TELEOP_SOCKET_PATH_TOO_LONG,
    TELEOP_STACK_START_FAILED,
    TELEOP_TEARDOWN_UNPROVEN,
    _digest,
    _read_json,
    _utc_now,
    acceptance_receipt,
    bridge_cleanup_receipt,
    check_socket_paths,
    e2e_block,
    read_closed_report,
    read_e2e_evidence,
    socket_paths,
    teardown_receipt,
    validate_receipt,
    verify_bundle,
)
from so101_demo.act.head_search_teleop_acceptance.runners import (
    TeleopAcceptanceRefused,
    _write,
    app_factory,
    detector_flight,
    e2e_runner,
    http_probe,
    real_ownership_probe,
    real_stack_factory,
)


class TeleopAcceptance:
    """One owned Teleop acceptance: start, probe, run the case, tear down, then write the receipt.

    Every side effect is a seam so the unit tests can drive the whole orchestration with synthetic
    fixtures and assert the *ordering*: nothing is written before its own evidence exists, and the
    receipt is written only after the teardown has been observed.
    """

    def __init__(
        self,
        *,
        run_root,
        acceptance_root,
        socket_root,
        ready_file,
        runtime: Mapping,
        bundle: Mapping,
        report: Mapping,
        values: Mapping,
        runtime_id: str,
        model_id: str,
        weights_path,
        device: str = "cuda",
        frames: int = DEFAULT_FRAME_PROBE,
        web_port: int = DEFAULT_WEB_PORT,
        scene_path=None,
        urdf_path=None,
        plugin_config_path=None,
        controller_config_path=None,
        frozen_candidate_path=None,
        operating_point: Mapping | None = None,
        app_environment: Mapping | None = None,
        app_command: Sequence[str] | None = None,
        static_dir=None,
        web_dir=None,
        profile: str = PROFILE,
        stack_factory=None,
        detector_flight=None,
        app_factory=None,
        app_probe=None,
        e2e_runner=None,
        ownership_probe=None,
        observer=None,
        clock=time.monotonic,
        sleep=time.sleep,
        stdout=None,
        stderr=None,
    ) -> None:
        self.run_root = Path(run_root)
        self.acceptance_root = Path(acceptance_root)
        self.socket_root = Path(socket_root)
        self.ready_file = Path(ready_file)
        self.runtime = dict(runtime)
        self.bundle = dict(bundle)
        self.report = dict(report)
        self.values = dict(values)
        self.runtime_id = str(runtime_id)
        self.model_id = str(model_id)
        self.weights_path = Path(weights_path)
        self.device = str(device)
        self.frames = int(frames)
        self.web_port = int(web_port)
        self.scene_path = None if scene_path is None else Path(scene_path)
        self.urdf_path = None if urdf_path is None else Path(urdf_path)
        self.plugin_config_path = None if plugin_config_path is None else Path(plugin_config_path)
        self.controller_config_path = (
            None if controller_config_path is None else Path(controller_config_path)
        )
        self.frozen_candidate_path = (
            None if frozen_candidate_path is None else Path(frozen_candidate_path)
        )
        self.operating_point = dict(operating_point or {})
        if not self.operating_point and "tracking_iou" in self.values:
            self.operating_point = {"iou": float(self.values["tracking_iou"])}
        self.app_environment = dict(app_environment or {})
        self.app_command = list(app_command or ())
        self.static_dir = None if static_dir is None else Path(static_dir)
        self.web_dir = None if web_dir is None else Path(web_dir)
        self.profile = str(profile)
        self.stack_factory = stack_factory
        self.detector_flight = detector_flight
        self.app_factory = app_factory
        self.app_probe = app_probe
        self.e2e_runner = e2e_runner
        self.ownership_probe = ownership_probe
        self.observer = observer
        self.clock = clock
        self.sleep = sleep
        self.stdout = stdout
        self.stderr = stderr
        self.checks: list[dict] = []
        self.refusals: list[dict] = []
        self.evidence: dict = {}

    # -- helpers ---------------------------------------------------------------------------------------

    def log(self, message: str) -> None:
        if self.stdout is not None:
            self.stdout.write(f"[{_utc_now()}] teleop-acceptance: {message}\n")
            self.stdout.flush()

    def warn(self, message: str) -> None:
        if self.stderr is not None:
            self.stderr.write(f"[{_utc_now()}] teleop-acceptance: {message}\n")
            self.stderr.flush()

    def check(self, name: str, ok: bool, detail: str, **extra) -> bool:
        entry = {"name": name, "status": PASSED if ok else FAILED, "detail": detail}
        entry.update(extra)
        self.checks.append(entry)
        if not ok:
            self.warn(f"check {name} FAILED: {detail}")
        return bool(ok)

    def refuse(self, code: str, detail: str, *, fatal: bool = False) -> None:
        self.refusals.append({"code": code, "detail": detail, "fatal": bool(fatal)})
        self.warn(f"{code}: {detail}")
        if fatal:
            raise TeleopAcceptanceRefused(code, detail)

    # -- the run ---------------------------------------------------------------------------------------

    def run(self) -> dict:
        started = self.clock()
        started_at = _utc_now()
        root = self.run_root
        if root.exists():
            raise TeleopAcceptanceRefused(
                TELEOP_RUN_ROOT_EXISTS, f"{root} already exists; a run has no resume"
            )
        root.mkdir(parents=True)
        self.acceptance_root.mkdir(parents=True, exist_ok=True)
        self.socket_root.mkdir(parents=True, exist_ok=True)
        _write(root, STATE_ARTIFACT, {"state": "RUNNING", "phase": "teleop-acceptance"})

        declared = self.declared_identity()
        sockets = check_socket_paths(socket_paths(self.socket_root))
        if not sockets["within_limit"]:
            self.refuse(
                TELEOP_SOCKET_PATH_TOO_LONG,
                f"the bridge endpoints must be {SOCKET_PATH_LIMIT_BYTES} bytes or fewer: "
                f"{sockets['path_bytes']} for {sockets['paths']}",
                fatal=True,
            )
        if not declared["values_match"]:
            self.refuse(
                TELEOP_BUNDLE_MISMATCH,
                f"the declared bundle's values digest to {declared['values_sha256']}, the promoted config "
                f"digests to {declared['promoted_values_sha256']}",
                fatal=True,
            )
        if not self.report.get("present"):
            self.refuse(
                TELEOP_REPORT_NOT_PUBLISHED,
                f"no closed head-only report exists at {self.report.get('path')!r}: the plan's Step 5 "
                "documents are published only when the nine qualification gates hold, and they do not",
            )
        elif self.report.get("status") != "HEAD_SEARCH_QUALIFIED":
            self.refuse(
                TELEOP_REPORT_NOT_CLOSED,
                f"the cited report is {self.report.get('status')!r}, not HEAD_SEARCH_QUALIFIED",
            )

        stack = None
        app = None
        owned_pids: list[int] = []
        before = self.observe()
        if before.get("processes") or before.get("nodes") or before.get("gpu_compute_apps"):
            self.refuse(
                TELEOP_OWNERSHIP_REFUSED,
                f"a second owner is active before the acceptance starts: processes="
                f"{before.get('processes')} nodes={before.get('nodes')} "
                f"gpu={before.get('gpu_compute_apps')}",
                fatal=True,
            )
        try:
            self.log("starting the one production composition")
            stack, flight = self.start_stack_and_detector()
            owned_pids.extend(self.stack_pids(stack))
            self.evidence["flight"] = flight
            connection = self.publish_connection(flight)
            self.evidence["connection"] = connection
            app = self.start_app(connection)
            owned_pids.extend(self.app_pids(app))
            status = self.await_app()
            self.evidence["app_status"] = status
            self.evidence["status"] = status
            probes = self.run_probes(status)
            self.evidence["probes"] = probes
            e2e_rc = self.run_e2e()
        finally:
            if app is not None:
                self.stop_app(app)
            if stack is not None:
                self.stop_stack(stack)

        after = self.observe()
        teardown = teardown_receipt(
            owned_pids=owned_pids,
            processes=after.get("processes") or (),
            nodes=after.get("nodes") or (),
            gpu_compute_apps=after.get("gpu_compute_apps") or (),
            before={"processes": before.get("processes"), "nodes": before.get("nodes")},
        )
        if not (
            teardown["controller_stopped"]
            and teardown["graph_clear"]
            and teardown["process_groups_exited"] >= 2
        ):
            self.refuse(
                TELEOP_TEARDOWN_UNPROVEN,
                f"the acceptance stack could not be proven gone: {teardown}",
            )
        if not teardown["gpu_released"]:
            self.refuse(
                TELEOP_GPU_NOT_RELEASED, "a compute process still held the GPU after the teardown"
            )
        self.evidence["teardown"] = teardown
        teardown_path = _write(root, TEARDOWN_ARTIFACT, teardown)

        cleanup = bridge_cleanup_receipt(
            socket_root=self.socket_root, declared_paths=sockets["paths"]
        )
        cleanup_path = _write(root, CLEANUP_ARTIFACT, cleanup)
        cleanup["cleanup_receipt"] = {"path": str(cleanup_path), "sha256": _digest(cleanup_path)}

        evidence = read_e2e_evidence(
            self.acceptance_root,
            report_path=self.acceptance_root / "reports" / "playwright-default.json",
        )
        e2e = e2e_block(evidence, command=E2E_COMMAND, rc=e2e_rc)
        if e2e["status"] != PASSED:
            self.refuse(
                TELEOP_E2E_FAILED if evidence.get("present") else TELEOP_E2E_EVIDENCE_MISSING,
                f"the installed case did not pass with fresh evidence: case={e2e['case']!r} "
                f"status={e2e['status']!r} rc={e2e['rc']!r} pairs={e2e['raw_overlay_pairs']} "
                f"screenshots={len(e2e['screenshots'])} missing={e2e['missing_screenshots'][:3]}",
            )

        detector = self.detector_block(flight)
        probes = self.evidence.get("probes") or {}
        if not all(entry.get("status") == PASSED for entry in probes.values()):
            failed = sorted(name for name, entry in probes.items() if entry.get("status") != PASSED)
            self.refuse(TELEOP_PROBE_FAILED, f"the head-camera probes did not all pass: {failed}")

        finished_at = _utc_now()
        receipt = acceptance_receipt(
            runtime=self.runtime,
            bundle_sha256=declared["sha256"],
            runtime_id=self.runtime_id,
            report=self.report,
            connection={
                **(self.evidence.get("connection") or {}),
                "sha256": _digest(self.ready_file),
            },
            detector=detector,
            probes=probes,
            e2e=e2e,
            teardown=teardown,
            bridge={
                "socket_root": str(self.socket_root),
                "socket_paths": sockets["paths"],
                "socket_path_bytes": sockets["path_bytes"],
                "cleanup_receipt": cleanup["cleanup_receipt"],
                "cleanup": cleanup,
            },
            checks=[dict(item) for item in self.checks],
            refusals=self.refusals,
            acceptance_root=self.acceptance_root,
            run_root=root,
            started_at_utc=started_at,
            finished_at_utc=finished_at,
            elapsed_s=self.clock() - started,
            profile=self.profile,
        )
        receipt["declared"] = {
            key: value for key, value in declared.items() if key != "parameter_names"
        }
        receipt["teardown_receipt"] = {"path": str(teardown_path), "sha256": _digest(teardown_path)}
        receipt["problems"] = validate_receipt(receipt)
        receipt_path = _write(self.acceptance_root, RECEIPT_ARTIFACT, receipt)
        _write(
            root,
            STATE_ARTIFACT,
            {
                "state": REFUSED if receipt["refusals"] else "SUCCEEDED",
                "phase": "teleop-acceptance",
                "receipt": str(receipt_path),
            },
        )
        self.log(
            f"receipt {receipt_path} status={receipt['status']} refusals={len(receipt['refusals'])}"
        )
        return receipt

    # -- the seams -------------------------------------------------------------------------------------

    def declared_identity(self) -> dict:
        """The declared bundle and the frozen runtime it was verified against, both read off disk."""

        return {**dict(self.runtime), **dict(self.bundle)}

    def observe(self) -> dict:
        if self.observer is None:
            return {"processes": [], "nodes": [], "gpu_compute_apps": [], "sim_clock_s": []}
        return dict(self.observer())

    def stack_pids(self, stack) -> list[int]:
        processes = getattr(stack, "processes", None) or []
        return [int(getattr(process, "pid", process)) for process in processes]

    def app_pids(self, app) -> list[int]:
        pid = getattr(app, "pid", None)
        return [] if pid is None else [int(pid)]

    def start_stack_and_detector(self):
        if self.stack_factory is None:
            raise TeleopAcceptanceRefused(
                TELEOP_STACK_START_FAILED, "no stack factory was supplied"
            )
        stack = self.stack_factory(
            urdf_path=self.urdf_path,
            scene_path=self.scene_path,
            plugin_config_path=self.plugin_config_path,
            controller_config_path=self.controller_config_path,
            workspace=self.run_root / "stack",
            session_id=self.session_id(),
            logger=lambda message: self.log(f"stack: {message}"),
        )
        try:
            stack.start()
        except Exception as error:  # noqa: BLE001 - a start failure is a named refusal
            raise TeleopAcceptanceRefused(TELEOP_STACK_START_FAILED, repr(error)) from error
        # once the stack is up this function owns its teardown: a failure below must not leave the
        # production composition running behind a refusal, which is exactly what a leaked child is
        try:
            return stack, self.probe_stack_frames(stack)
        except BaseException:
            self.stop_stack(stack)
            raise

    def probe_stack_frames(self, stack) -> dict:
        if self.detector_flight is None:
            raise TeleopAcceptanceRefused(
                TELEOP_DETECTOR_FAILED, "no head-camera flight was supplied"
            )
        try:
            flight = dict(
                self.detector_flight(
                    session_id=self.session_id(),
                    values=self.values,
                    weights_path=self.weights_path,
                    model_id=self.model_id,
                    device=self.device,
                    frames=self.frames,
                    operating_point=self.operating_point,
                    log=self.log,
                )
            )
        except Exception as error:  # noqa: BLE001 - a detector failure is a named refusal
            raise TeleopAcceptanceRefused(TELEOP_DETECTOR_FAILED, repr(error)) from error
        if not self.check(
            "one_cuda_detector",
            int(flight.get("detector_count", 0)) == 1
            and str(flight.get("runtime_device", "")) == self.device
            and flight.get("allow_cpu_fallback") is False,
            f"the acceptance constructed {flight.get('detector_count')} detector(s) on "
            f"{flight.get('runtime_device')!r} with allow_cpu_fallback="
            f"{flight.get('allow_cpu_fallback')!r}",
            frames=flight.get("frames"),
        ):
            raise TeleopAcceptanceRefused(
                TELEOP_DETECTOR_FAILED, "the acceptance did not prove one CUDA detector"
            )
        if not self.check(
            "head_camera_frames",
            int(flight.get("frame_count", 0)) >= 1,
            f"the detector consumed {flight.get('frame_count')} real frames at "
            f"{flight.get('frame_rate_hz')} Hz",
        ):
            raise TeleopAcceptanceRefused(
                TELEOP_FRAME_PROBE_FAILED, "the head camera published no frame to the detector"
            )
        return flight

    def session_id(self) -> str:
        return f"{self.runtime_id}-acceptance"

    def connection_document(self, flight: Mapping) -> dict:
        from so101_demo.act.head_search_qualification import process_start_ticks

        interval = self.values.get("lock_valid_neck_rad") or [-0.1756, 0.0805]
        return {
            "operation": OPERATION,
            "kind": "head_search_teleop_connection",
            "runtime_id": self.runtime_id,
            "head_search_runtime_id": self.runtime_id,
            "simulation_session_id": self.session_id(),
            "execution_generation": 1,
            "model_id": self.model_id,
            "bundle_sha256": str(self.bundle.get("sha256", "")),
            "source_commit": self.runtime.get("source_commit"),
            "safe_interval_rad": [float(interval[0]), float(interval[1])],
            "bridge_socket_root": str(self.socket_root),
            "head_camera_topic": HEAD_CAMERA_IMAGE_TOPIC,
            "head_camera_frame_rate_hz": flight.get("frame_rate_hz"),
            "owner": {
                "pid": os.getpid(),
                "started_ticks": process_start_ticks(),
                "argv_sha256": hashlib.sha256(" ".join(os.sys.argv).encode("utf-8")).hexdigest(),
            },
        }

    def publish_connection(self, flight: Mapping) -> dict:
        document = self.connection_document(flight)
        self.ready_file.parent.mkdir(parents=True, exist_ok=True)
        self.ready_file.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write(self.run_root, CONNECTION_ARTIFACT, document)
        self.log(f"connection descriptor {self.ready_file}")
        return document

    def app_env(self) -> dict:
        environment = dict(os.environ)
        environment.update(self.app_environment)
        environment.setdefault("SO101_UNIFIED_RUNTIME_ID", self.runtime_id)
        environment.setdefault("SO101_UNIFIED_SOCKET_DIR", str(self.socket_root))
        environment.setdefault("SO101_HEAD_CAMERA_CONNECTION", str(self.ready_file))
        environment.setdefault("SO101_UNIFIED_EVIDENCE_ROOT", str(self.acceptance_root))
        environment.setdefault("SO101_UNIFIED_BACKEND", "mujoco_py")
        return environment

    def start_app(self, connection: Mapping) -> object:
        if self.app_factory is None:
            raise TeleopAcceptanceRefused(
                TELEOP_APP_NOT_SERVED, "no unified app factory was supplied"
            )
        try:
            app = self.app_factory(
                command=list(self.app_command),
                environment=self.app_env(),
                port=self.web_port,
                capture_dir=self.acceptance_root / "captures",
                static_dir=self.static_dir,
                stdout_path=self.acceptance_root / "server.log",
            )
        except Exception as error:  # noqa: BLE001 - a start failure is a named refusal
            raise TeleopAcceptanceRefused(TELEOP_APP_NOT_SERVED, repr(error)) from error
        self.log(f"unified app pid {getattr(app, 'pid', None)} on port {self.web_port}")
        return app

    def await_app(self) -> dict:
        if self.app_probe is None:
            raise TeleopAcceptanceRefused(TELEOP_APP_NOT_SERVED, "no app probe was supplied")
        base_url = f"http://127.0.0.1:{self.web_port}"
        deadline = self.clock() + APP_START_TIMEOUT_S
        status = None
        while self.clock() < deadline:
            status = self.app_probe({"action": "status", "base_url": base_url})
            if status.get("ok"):
                break
            self.sleep(1.0)
        if not status or not status.get("ok"):
            raise TeleopAcceptanceRefused(
                TELEOP_APP_NOT_SERVED,
                f"the head-camera status route never answered 200: {status}",
            )
        self.check(
            "served_status_route",
            status.get("status") == 200,
            f"GET /teleop/head-camera/status answered {status.get('status')}",
        )
        body = status.get("body") or {}
        self.check(
            "served_identity",
            body.get("available") is True
            and body.get("operation") == OPERATION
            and body.get("runtime_id") == self.runtime_id
            and str(body.get("model_id") or "") == self.model_id,
            f"the served status repeats operation/runtime/model: {body}",
            body=body,
        )
        return body

    def run_probes(self, status: Mapping) -> dict:
        if self.app_probe is None:
            raise TeleopAcceptanceRefused(TELEOP_PROBE_FAILED, "no app probe was supplied")
        base_url = f"http://127.0.0.1:{self.web_port}"
        interval = list(status.get("safe_interval_rad") or self.connection_interval())
        self.evidence["served_interval"] = interval
        low, high = float(interval[0]), float(interval[1])
        inside = (low + high) / 2.0
        outside = high + max(1.0, (high - low))
        observations = {
            "capture_no_frame": self.app_probe({"action": "capture", "base_url": base_url}),
            "target_sealed_interval": self.app_probe(
                {
                    "action": "target",
                    "base_url": base_url,
                    "payload": {"target_rad": inside, "safe_interval_rad": [low, high]},
                }
            ),
            "target_out_of_range": self.app_probe(
                {"action": "target", "base_url": base_url, "payload": {"target_rad": outside}}
            ),
            "target_bounded": self.app_probe(
                {"action": "target", "base_url": base_url, "payload": {"target_rad": inside}}
            ),
            "stop_stopping": self.app_probe(
                {
                    "action": "stop",
                    "base_url": base_url,
                    "payload": {"neck_velocity_rad_s": 0.0, "sim_time_s": 1.0},
                }
            ),
            "stop_proof": self.stop_proof(self.app_probe, base_url),
            "stop_replay_resets": self.app_probe(
                {
                    "action": "stop",
                    "base_url": base_url,
                    "payload": {"neck_velocity_rad_s": 0.0, "sim_time_s": 1.0},
                }
            ),
        }
        probes = {
            name: self.probe_block(
                name, observation, low=low, high=high, inside=inside, outside=outside
            )
            for name, observation in observations.items()
        }
        return probes

    def stop_proof(self, probe, base_url: str) -> dict:
        """Three consecutive fresh raw samples, each through the installed route."""

        samples = []
        for index in range(2, 2 + STOP_SAMPLES):
            samples.append(
                probe(
                    {
                        "action": "stop",
                        "base_url": base_url,
                        "payload": {"neck_velocity_rad_s": 0.0, "sim_time_s": float(index)},
                    }
                )
            )
        return {"ok": all(item.get("ok") for item in samples), "samples": samples}

    def connection_interval(self) -> list[float]:
        interval = self.values.get("lock_valid_neck_rad") or [-0.1756, 0.0805]
        return [float(interval[0]), float(interval[1])]

    def probe_block(self, name: str, observation: Mapping, *, low, high, inside, outside) -> dict:
        body = observation.get("body") or {}
        # the app's structured-error handler unwraps `HTTPException.detail`, so the refusal arrives as
        # the code mapping itself; a wrapped body is accepted too rather than assumed away
        wrapped = (body.get("detail") or {}) if isinstance(body, Mapping) else {}
        code = (body.get("code") if isinstance(body, Mapping) else None) or (
            wrapped.get("code") if isinstance(wrapped, Mapping) else None
        )
        ok = False
        detail = ""
        if name == "capture_no_frame":
            ok = observation.get("status") == 409 and code == "HEAD_CAPTURE_NO_FRAME"
            detail = f"capture before any frame refused with {code!r}"
        elif name == "target_sealed_interval":
            ok = observation.get("status") == 409 and code == "HEAD_TARGET_INTERVAL_SEALED"
            detail = f"a caller-supplied interval was refused with {code!r}"
        elif name == "target_out_of_range":
            ok = observation.get("status") == 409 and code == "HEAD_TARGET_OUT_OF_RANGE"
            detail = f"the absolute bound refused {outside} with {code!r}"
        elif name == "target_bounded":
            ok = (
                observation.get("ok") is True
                and abs(float(body.get("submitted_rad", 1e9)) - inside) < 1e-9
                and body.get("status") == "SUBMITTED"
            )
            detail = f"the sealed interval accepted {inside} and echoed it"
        elif name == "stop_stopping":
            ok = observation.get("ok") is True and body.get("state") == "STOPPING"
            detail = f"one accepted sample reports {body.get('state')!r}, never STOPPED"
        elif name == "stop_proof":
            last = (observation.get("samples") or [{}])[-1].get("body") or {}
            ok = (
                observation.get("ok") is True
                and last.get("state") == "STOPPED"
                and int(last.get("consecutive_samples", 0)) >= STOP_SAMPLES
            )
            detail = (
                f"three consecutive fresh samples ended {last.get('state')!r} at "
                f"{last.get('consecutive_samples')} samples"
            )
        elif name == "stop_replay_resets":
            ok = observation.get("ok") is True and int(body.get("consecutive_samples", 1)) == 0
            detail = f"a replayed sim_time_s reset the proof to {body.get('consecutive_samples')}"
        self.check(f"probe_{name}", bool(ok), detail)
        return {
            "status": PASSED if ok else FAILED,
            "detail": detail,
            "http_status": observation.get("status"),
            "code": code,
            "response": body,
        }

    def run_e2e(self) -> int | None:
        if self.e2e_runner is None:
            self.refuse(TELEOP_E2E_EVIDENCE_MISSING, "no e2e runner was supplied")
            self.evidence["e2e_rc"] = None
            return None
        result = dict(
            self.e2e_runner(
                base_url=f"http://127.0.0.1:{self.web_port}",
                evidence_root=self.acceptance_root,
                web_dir=self.web_dir,
                stdout_path=self.acceptance_root / "e2e.log",
                stderr_path=self.acceptance_root / "e2e.err.log",
            )
        )
        rc = result.get("rc")
        self.evidence["e2e_rc"] = rc
        self.evidence["e2e_command"] = result.get("command")
        self.check(
            "e2e_case",
            rc == 0,
            f"{result.get('command')} returned rc={rc}",
            rc=rc,
        )
        return rc

    def stop_app(self, app) -> None:
        self.log("stopping the unified app")
        if self.app_factory is None:
            return
        try:
            app.terminate()
        except Exception as error:  # noqa: BLE001 - a stop failure is verified, not asserted
            self.warn(f"the app terminate raised {error!r}")
        try:
            app.wait(timeout=APP_STOP_TIMEOUT_S)
        except Exception:  # noqa: BLE001 - the observation below decides, not this call
            self.warn("the app did not exit within its budget; killing its process group")
            pid = getattr(app, "pid", None)
            if pid is not None:
                try:
                    os.killpg(int(pid), signal.SIGKILL)
                except OSError as error:
                    self.warn(f"the group kill raised {error!r}")
            try:
                app.wait(timeout=APP_STOP_TIMEOUT_S)
            except Exception as error:  # noqa: BLE001 - the teardown proof is what decides
                self.warn(f"the app still did not exit: {error!r}")

    def stop_stack(self, stack) -> None:
        self.log("stopping the production composition")
        try:
            stack.stop()
        except Exception as error:  # noqa: BLE001 - a stop failure is verified, not asserted
            self.warn(f"the stack stop raised {error!r}")

    def detector_block(self, flight: Mapping) -> dict:
        return {
            "count": int(flight.get("detector_count", 0)),
            "teleop_detector_factory_count": self.evidence.get("teleop_detector_factory_count", 0),
            "device": flight.get("runtime_device"),
            "allow_cpu_fallback": flight.get("allow_cpu_fallback"),
            "weights_sha256": flight.get("weights_sha256"),
            "model_id": self.model_id,
            "frame_count": int(flight.get("frame_count", 0)),
            "detections": int(flight.get("detections", 0)),
            "frame_rate_hz": flight.get("frame_rate_hz"),
            "source": flight.get("source")
            or f"the acceptance's own production detector over {HEAD_CAMERA_IMAGE_TOPIC}",
        }


def acceptance_environment(
    *,
    final_run,
    evidence_root,
    runtime_id: str,
    socket_root,
    connection,
    ros_python,
    base: Mapping | None = None,
) -> dict:
    """The plan's own seven declarations for the installed app, verbatim."""

    environment = dict(os.environ if base is None else base)
    environment.update(
        {
            "SO101_UNIFIED_BACKEND": "mujoco_py",
            "SO101_UNIFIED_INSTALL_PREFIX": str(Path(final_run) / "install"),
            "SO101_UNIFIED_EVIDENCE_ROOT": str(evidence_root),
            "SO101_UNIFIED_RUNTIME_ID": str(runtime_id),
            "SO101_UNIFIED_SOCKET_DIR": str(socket_root),
            "SO101_HEAD_CAMERA_CONNECTION": str(connection),
            "SO101_UNIFIED_ROS_PYTHON": str(ros_python),
        }
    )
    return environment


def installed_paths(final_run) -> dict:
    """The frozen install's own composition inputs, each asserted to exist before it is declared."""

    root = Path(final_run)
    share = root / "install" / "so101_demo_py" / "share" / "so101_demo_py"
    teleop = root / "install" / "so101_teleop"
    declared = {
        "scene": share / "assets" / "mujoco" / "act" / "head_search_scene.xml",
        "urdf": share / "assets" / "mujoco" / "act" / "so101.urdf",
        "plugin_config": share / "config" / "mujoco" / "act" / "mujoco_plugins.yaml",
        "controller_config": share / "config" / "mujoco" / "act" / "ros2_controllers.yaml",
        "app": teleop / "lib" / "so101_teleop" / "so101_unified_web_server.py",
        "web_bundle": teleop / "share" / "so101_teleop" / "web" / "index.html",
    }
    missing = [name for name, path in declared.items() if not Path(path).exists()]
    if missing:
        raise ValueError(f"{TELEOP_INPUTS_INCOMPLETE}: the frozen install is missing {missing}")
    return {name: Path(path) for name, path in declared.items()}


def accept_teleop(
    *,
    run_root,
    acceptance_root,
    socket_root,
    ready_file,
    final_run,
    production_config,
    approved_bundle,
    approval_receipt=None,
    qualification_report=None,
    runtime_id,
    profile: str = PROFILE,
    device: str = "cuda",
    frames: int = DEFAULT_FRAME_PROBE,
    web_port: int = DEFAULT_WEB_PORT,
    weights_path=None,
    frozen_candidate=None,
    expected: Mapping | None = None,
    web_dir=None,
    ros_python=None,
    stdout=None,
    stderr=None,
) -> dict:
    """Assemble and run the real acceptance: the one entry point ``serve-teleop`` calls."""

    from so101_demo.act.head_search_restarts.observation import read_runtime_of_record

    # the run root is claimed by the acceptance itself, first thing, so a refused input can never leave
    # a half-created run root behind and two starts can never both believe they won it
    root = Path(run_root)
    acceptance = Path(acceptance_root)
    bundle = verify_bundle(bundle_path=approved_bundle, production_config=production_config)
    runtime = read_runtime_of_record(final_run, production_config=production_config)
    if approval_receipt is not None and not Path(approval_receipt).is_file():
        raise TeleopAcceptanceRefused(
            TELEOP_INPUTS_INCOMPLETE, f"the approval receipt {approval_receipt} is absent"
        )
    for key, value in dict(expected or {}).items():
        if value is None:
            continue
        if str(runtime.get(key)) != str(value):
            raise TeleopAcceptanceRefused(
                TELEOP_RUNTIME_UNVERIFIED,
                f"the frozen runtime's {key} is {runtime.get(key)!r}, the expected value is {value!r}",
            )
    document = _read_json(production_config) or {}
    values = dict(document.get("values") or {})
    operating_point = {}
    if frozen_candidate is not None:
        from so101_demo.act.head_search_restarts.search_flight import _operating_point

        operating_point = dict(_operating_point(frozen_candidate))
    weights = Path(weights_path or runtime.get("weight_path") or "")
    paths = installed_paths(final_run)
    python = (
        Path(ros_python) if ros_python else Path(os.environ.get("SO101_UNIFIED_ROS_PYTHON") or "")
    )
    return TeleopAcceptance(
        run_root=root,
        acceptance_root=acceptance,
        socket_root=socket_root,
        ready_file=ready_file,
        runtime=runtime,
        bundle=bundle,
        report=read_closed_report(qualification_report),
        values=values,
        runtime_id=runtime_id,
        model_id=str(document.get("runtime_id") or "head-search-runtime"),
        weights_path=weights,
        device=device,
        frames=frames,
        web_port=web_port,
        scene_path=paths["scene"],
        urdf_path=paths["urdf"],
        plugin_config_path=paths["plugin_config"],
        controller_config_path=paths["controller_config"],
        frozen_candidate_path=frozen_candidate,
        operating_point=operating_point,
        app_environment=acceptance_environment(
            final_run=final_run,
            evidence_root=acceptance,
            runtime_id=runtime_id,
            socket_root=socket_root,
            connection=ready_file,
            ros_python=python,
        ),
        app_command=[str(paths["app"])],
        static_dir=paths["web_bundle"].parent,
        web_dir=web_dir,
        profile=profile,
        stack_factory=real_stack_factory,
        detector_flight=detector_flight,
        app_factory=app_factory,
        app_probe=http_probe,
        e2e_runner=e2e_runner,
        observer=real_ownership_probe,
        stdout=stdout,
        stderr=stderr,
    ).run()
