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
                if self.process.poll() is not None:
                    raise PolicyServiceError(f"POLICY_SERVICE_EXITED_BEFORE_READY: {self.process.returncode}")
                if self.clock() >= deadline:
                    raise PolicyServiceError("POLICY_SERVICE_READY_TIMEOUT")
                self.sleep(0.1)
            self.record = _read_json(self.record_dir / "process-record.json")
            self.ready = _read_json(ready)
            self._check_started()
        except BaseException:
            self.kill()
            raise
        write_json(self.home / "host-start.json", {"record": self.record, "ready": self.ready, "pid": self.process.pid})
        return self.ready

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
        """True only while the started process is alive, is still the process that was proved, and answers a health query."""
        if self.process is None or self.process.poll() is not None or self.record is None:
            return False
        try:
            live = self.identity_of(self.record["pid"])
            if any(self.record[name] != live[name] for name in ("pgid", "start_ticks", "argv_sha256")):
                return False
            return self.health_probe is None or self.health_probe() is True
        except (OSError, ValueError, KeyError):
            return False

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
            errors.append("POLICY_SERVICE_STOP_PROOF_MISSING")
        if proof is not None and (proof.get("terminated") is not True or proof.get("pid") != process.pid):
            errors.append("POLICY_SERVICE_STOP_PROOF_UNCONFIRMED")
        if code != 0:
            errors.append(f"POLICY_SERVICE_EXIT_CODE: {code}")
        self.stop_result = {"confirmed": not errors and not forced, "started": True, "pid": process.pid, "exit_code": code,
                            "forced": forced, "stop_proof_sha256": proof_sha, "stop_proof": proof, "errors": errors}
        write_json(self.home / "host-stop.json", self.stop_result)
        return self.stop_result
