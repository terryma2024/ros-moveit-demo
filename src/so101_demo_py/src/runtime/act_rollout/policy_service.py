"""The Host's ownership of the ACT policy service process: start, readiness, health, and the stop with its proof.

The service (`cli/act_policy_service.py`) is a Host process in the training interpreter, one per run. This owner starts it in its own
process group with a minimal environment and its output in the run's `services/policy/`, waits for the service's own readiness record,
proves that the process that wrote it is the one it started (pid, start ticks, argv hash against /proc) and that it serves the bundle
the run is bound to, and later stops exactly that process: SIGTERM after the identity is re-proved, then the service's own stop proof.
A process that does not stop in time is killed and the stop is then NOT confirmed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from so101_demo.runtime.act_policy.service import process_record, write_json

#: the only variables the service inherits; ROS and gate environments must not reach the training interpreter
INHERITED_ENVIRONMENT = ("PATH", "HOME", "LANG", "LC_ALL", "USER", "LOGNAME")


class PolicyServiceError(RuntimeError):
    """The service did not start, is not what the run is bound to, or did not stop."""


def _read_json(path):
    return json.loads(Path(path).read_bytes())


def service_environment(*, pythonpath, gpu_uuid, tmp, base=None):
    base = os.environ if base is None else base
    environment = {name: base[name] for name in INHERITED_ENVIRONMENT if name in base}
    environment.update(PYTHONPATH=str(pythonpath), CUDA_VISIBLE_DEVICES=gpu_uuid, PYTHONNOUSERSITE="1",
                       PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(tmp), TMP=str(tmp), TEMP=str(tmp))
    return environment


class PolicyServiceOwner:
    def __init__(self, *, run, python, pythonpath, bundle_dir, gpu_uuid, generation, expected, max_inflight=8,
                 queue_timeout_s=1.0, inference_timeout_s=0.5, warm_up_calls=3, undeclared_cameras=("head", "wrist"),
                 start_timeout_s=300.0, stop_timeout_s=30.0, command=None, popen=subprocess.Popen, clock=time.monotonic,
                 sleep=time.sleep, signal_process=os.kill, identity_of=process_record, health_probe=None, environ=None):
        self.run, self.python, self.pythonpath = Path(run), Path(python), Path(pythonpath)
        self.bundle_dir, self.gpu_uuid, self.generation = Path(bundle_dir), gpu_uuid, generation
        self.expected = dict(expected)          # bundle_sha256, policy_sha256, cameras, state_dim, image_shape
        self.options = dict(max_inflight=max_inflight, queue_timeout_s=queue_timeout_s, inference_timeout_s=inference_timeout_s,
                            warm_up_calls=warm_up_calls, undeclared_cameras=",".join(undeclared_cameras))
        self.start_timeout_s, self.stop_timeout_s = start_timeout_s, stop_timeout_s
        self.command = list(command) if command is not None else None
        self.popen, self.clock, self.sleep = popen, clock, sleep
        self.signal_process, self.identity_of, self.health_probe, self.environ = signal_process, identity_of, health_probe, environ
        self.home = self.run / "services" / "policy"
        self.socket_dir = self.run / "ipc" / "policy"
        self.socket = self.socket_dir / "policy.sock"
        self.record_dir = self.home / "record"
        self.process = None
        #: `stop()` (an interrupted run) sets this and waits for `start()` to end; `start()` then kills what it started
        self._abort = threading.Event()
        self._start_lock = threading.Lock()
        self.unhealthy_reason = None
        self.start_failed = False
        self.record = self.ready = self.stop_result = None
        self._streams = []

    # ---- start -------------------------------------------------------------------------------------------------------------

    def argv(self):
        base = self.command if self.command is not None else [str(self.python), "-s", "-B", "-m",
                                                               "so101_demo.cli.act_policy_service"]
        return [*base, "--bundle-dir", str(self.bundle_dir), "--socket", str(self.socket), "--record-dir", str(self.record_dir),
                "--generation", self.generation, "--gpu-uuid", self.gpu_uuid,
                "--max-inflight", str(self.options["max_inflight"]), "--queue-timeout-s", str(self.options["queue_timeout_s"]),
                "--inference-timeout-s", str(self.options["inference_timeout_s"]),
                "--warm-up-calls", str(self.options["warm_up_calls"]),
                "--undeclared-cameras", self.options["undeclared_cameras"]]

    def prepare(self):
        """The private directories; refuses to reuse a service directory or a socket."""
        for directory in (self.home, self.socket_dir):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        (self.home / "tmp").mkdir(mode=0o700, exist_ok=True)
        if self.record_dir.exists() or self.socket.exists() or any(self.socket_dir.iterdir()):
            raise PolicyServiceError("POLICY_SERVICE_DIRECTORY_NOT_NEW")

    def start(self):
        with self._start_lock:
            return self._start()

    def _start(self):
        if self._abort.is_set():
            raise PolicyServiceError("POLICY_SERVICE_START_ABORTED")
        if self.process is not None:
            raise PolicyServiceError("POLICY_SERVICE_ALREADY_STARTED")
        self.prepare()
        argv = self.argv()
        environment = service_environment(pythonpath=self.pythonpath, gpu_uuid=self.gpu_uuid, tmp=self.home / "tmp",
                                          base=self.environ)
        write_json(self.home / "launch.json", {"argv": argv, "environment": environment, "generation": self.generation,
                                               "started_wall_ns": time.time_ns()})
        out, err = (self.home / "service.out").open("xb"), (self.home / "service.err").open("xb")
        self._streams = [out, err]
        self.process = self.popen(argv, env=environment, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                  start_new_session=True, close_fds=True)
        deadline = self.clock() + self.start_timeout_s
        ready = self.record_dir / "ready.json"
        try:
            while not ready.exists():
                if self._abort.is_set():
                    raise PolicyServiceError("POLICY_SERVICE_START_ABORTED")
                if self.process.poll() is not None:
                    raise PolicyServiceError(f"POLICY_SERVICE_EXITED_BEFORE_READY: {self.process.returncode}")
                if self.clock() >= deadline:
                    raise PolicyServiceError("POLICY_SERVICE_READY_TIMEOUT")
                self.sleep(0.1)
            self.record = self._read_until(self.record_dir / "process-record.json", deadline)
            self.ready = self._read_until(ready, deadline)
            self._check_started()
        except BaseException:
            self.start_failed = True
            self.kill()
            raise
        write_json(self.home / "host-start.json", {"record": self.record, "ready": self.ready, "pid": self.process.pid})
        return self.ready

    def _read_until(self, path, deadline):
        """The JSON in `path`, parsed again until it parses or the start deadline passes (a writer that is not atomic is half read)."""
        while True:
            try:
                return _read_json(path)
            except (ValueError, OSError) as error:
                if self.process.poll() is not None:
                    raise PolicyServiceError(f"POLICY_SERVICE_EXITED_BEFORE_READY: {self.process.returncode}") from error
                if self.clock() >= deadline:
                    raise PolicyServiceError(f"POLICY_SERVICE_RECORD_UNREADABLE: {path.name}") from error
                self.sleep(0.02)

    def _check_started(self):
        record, ready, expected = self.record, self.ready, self.expected
        live = self.identity_of(record["pid"])
        if (record["pid"] != self.process.pid or record["kind"] != "ACT_POLICY_SERVICE_PROCESS"
                or any(record[name] != live[name] for name in ("pgid", "start_ticks", "argv_sha256"))
                or record["generation"] != self.generation):
            raise PolicyServiceError("POLICY_SERVICE_IDENTITY_MISMATCH")
        if (ready.get("ready") is not True or ready["service_generation"] != self.generation
                or ready["bundle_sha256"] != expected["bundle_sha256"] or ready["policy_sha256"] != expected["policy_sha256"]
                or list(ready["cameras"]) != list(expected["cameras"]) or ready["state_dim"] != expected["state_dim"]
                or list(ready["image_shape"]) != list(expected["image_shape"]) or ready["socket"] != str(self.socket)
                or ready["pid"] != record["pid"]):
            raise PolicyServiceError("POLICY_SERVICE_BUNDLE_MISMATCH")

    # ---- while it runs -----------------------------------------------------------------------------------------------------

    def healthy(self):
        """True only while the started process is alive, is still the process that was proved, and its health probe says so.

        The probe returns True, or says why not (a string, or just a falsy value); `unhealthy_reason` keeps the first reason."""
        reason = self._unhealthy()
        if reason is not None and self.unhealthy_reason is None:
            self.unhealthy_reason = reason
        return reason is None

    def _unhealthy(self):
        if self.process is None or self.record is None:
            return "NOT_STARTED"
        if self.process.poll() is not None:
            return f"PROCESS_EXITED: {self.process.returncode}"
        try:
            live = self.identity_of(self.record["pid"])
            if any(self.record[name] != live[name] for name in ("pgid", "start_ticks", "argv_sha256")):
                return "PROCESS_IDENTITY_CHANGED"
            if self.health_probe is None:
                return None
            answer = self.health_probe()
            return None if answer is True else (answer if isinstance(answer, str) and answer else "HEALTH_PROBE_FALSE")
        except (OSError, ValueError, KeyError) as error:
            return f"HEALTH_CHECK_ERROR: {type(error).__name__}: {error}"[:200]

    # ---- stop --------------------------------------------------------------------------------------------------------------

    def kill(self):
        process = self.process
        if process is not None and process.poll() is None:
            try:
                self.signal_process(process.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                process.wait(timeout=10)
            except Exception:       # noqa: BLE001 - reported by the stop proof
                pass

    def stop(self):
        """Stop the service this owner started and prove it; `confirmed` only with a clean exit and the service's own proof."""
        # an interrupted run: let a start in progress notice, kill what it started and return, before the stop is judged
        self._abort.set()
        with self._start_lock:
            return self._stop()

    def _stop(self):
        if self.stop_result is not None:
            return self.stop_result
        errors, forced, code = [], False, None
        process = self.process
        if process is None:
            self.stop_result = {"confirmed": True, "started": False, "errors": []}
            return self.stop_result
        try:
            if process.poll() is None:
                live = self.identity_of(process.pid) if self.record is not None else None
                if live is not None and any(self.record[name] != live[name] for name in ("pgid", "start_ticks", "argv_sha256")):
                    errors.append("POLICY_SERVICE_IDENTITY_CHANGED_BEFORE_STOP")
                else:
                    self.signal_process(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=self.stop_timeout_s)
                    except subprocess.TimeoutExpired:
                        forced = True
                        errors.append("POLICY_SERVICE_STOP_TIMEOUT")
                        self.kill()
        except (OSError, ValueError) as error:
            errors.append(f"{type(error).__name__}: {error}")
        code = process.poll()
        for stream in self._streams:
            try:
                stream.close()
            except OSError:
                pass
        proof, proof_sha = None, None
        try:
            raw = (self.record_dir / "stop-proof.json").read_bytes()
            proof, proof_sha = json.loads(raw), hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError):
            if not self.start_failed:
                errors.append("POLICY_SERVICE_STOP_PROOF_MISSING")
        if proof is not None and (proof.get("terminated") is not True or proof.get("pid") != process.pid):
            errors.append("POLICY_SERVICE_STOP_PROOF_UNCONFIRMED")
        if code != 0 and not self.start_failed:
            errors.append(f"POLICY_SERVICE_EXIT_CODE: {code}")
        if code is None:
            errors.append("POLICY_SERVICE_STILL_RUNNING")
        # A service that never became ready has no stop proof to give: it is stopped when the process is gone (its start killed it,
        # or it exited by itself), and the start failure is the run's fault.
        self.stop_result = {"confirmed": not errors and not forced, "started": True, "pid": process.pid, "exit_code": code,
                            "forced": forced, "start_failed": self.start_failed, "stop_proof_sha256": proof_sha,
                            "stop_proof": proof, "errors": errors}
        write_json(self.home / "host-stop.json", self.stop_result)
        return self.stop_result


def service_health_probe(client, *, max_consecutive_errors=3, max_unanswered=3):
    """The health probe of a running service: it answers a `policy_health_query` with `available` true and fewer than
    `max_consecutive_errors` replies in a row that said the service or the request is wrong.

    A service that faulted (`available` false: every request is answered INFRA_ERROR) or that answers a run of errors is unhealthy at
    once. A query that gets no answer is unhealthy after `max_unanswered` in a row (one slow answer is not a fault)."""
    unanswered = {"count": 0}

    def probe():
        try:
            reply = client.query("policy_health_query", timeout_s=2.0)
        except (OSError, ValueError, TimeoutError) as error:
            unanswered["count"] += 1
            if unanswered["count"] >= max_unanswered:
                return f"HEALTH_QUERY_UNANSWERED: {unanswered['count']} in a row: {type(error).__name__}"
            return True
        unanswered["count"] = 0
        if reply["available"] is not True:
            return f"POLICY_SERVICE_FAULT: {reply['reason']}"
        if reply["consecutive_errors"] >= max_consecutive_errors:
            return f"POLICY_SERVICE_ERRORS: {reply['consecutive_errors']} replies in a row were errors"
        return True
    return probe

