"""Own a record-only sidecar around the existing Teacher/Recorder flow during the pilot."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .raw_recorder import READY_SCHEMA, _atomic_json


class PilotRecording:
    def __init__(self, *, processes, root, environment, spec_factory, timeout_s=10.0,
                 clock=time.monotonic, sleep=time.sleep):
        self.processes = processes
        self.root = Path(root)
        self.environment = environment
        self.spec_factory = spec_factory
        self.timeout_s = timeout_s
        self.clock, self.sleep = clock, sleep
        self.identity = None
        self.ready = False
        self.failure = None

    def start(self):
        try:
            self.root.mkdir(parents=True, exist_ok=False)
            argv = (sys.executable, "-m", "so101_demo.act.offline.raw_recorder", "--bag-dir", str(self.root / "bag"),
                    "--scene-reads", str(self.root / "scene-reads.jsonl"), "--ready-file", str(self.root / "ready.json"),
                    "--stats-file", str(self.root / "record-stats.json"), "--ready-timeout-s", str(self.timeout_s))
            self.identity = self.processes.start(self.spec_factory(argv), environment=self.environment)
            deadline = self.clock() + self.timeout_s + 2.0
            while self.clock() < deadline:
                try:
                    document = json.loads((self.root / "ready.json").read_bytes())
                except (OSError, ValueError):
                    document = {}
                if document.get("schema") == READY_SCHEMA:
                    self.ready = document.get("state") == "RECORDING"
                    if not self.ready:
                        self.failure = "RAW_PILOT_NOT_RECORDING"
                    return
                if self.processes.exit_code(self.identity) is not None:
                    self.failure = "RAW_PILOT_EXITED_BEFORE_READY"
                    return
                self.sleep(0.02)
            self.failure = "RAW_PILOT_READY_TIMEOUT"
        except Exception as error:
            self.failure = "RAW_PILOT_START_FAILED: " + str(error)[:300]

    def finish(self):
        facts = {"ready": self.ready, "failure": self.failure}
        if self.identity is not None:
            try:
                facts["rc"] = self.processes.terminate(self.identity, 20.0)
                self.processes.stop(self.identity)
                facts.update(json.loads((self.root / "record-stats.json").read_bytes()))
            except Exception as error:
                facts["failure"] = "RAW_PILOT_STOP_FAILED: " + str(error)[:300]
        if self.root.is_dir():
            _atomic_json(self.root / "pilot-result.json", facts)
        return facts
