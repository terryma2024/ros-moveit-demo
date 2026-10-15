"""Phase 2 of a native single worker end to end: the real scheduler, the native processor launcher and owner, and the real processor
program in a real subprocess that leads a process group of its own.

The scene's phase-1 record is not there (no `result.json`), so the processor program refuses the task: the point here is the chain,
not the offline processor. The chain is the container chain's: the launch, the durable intent, the control channel, one task
assigned and its result read from the output directory, the refusal journaled as a fault, and the processor terminated and proven
stopped by the absence of its process tree before the summary exists.
"""

import asyncio
import hashlib
import json
import os
import shutil
import signal
import sys
import time

import pytest

from native_processor_world import SOURCE_ROOT
from so101_demo.runtime.container_campaign.native_stop import marker_survivors
from so101_demo.runtime.container_campaign.native_launcher import NativeProcessorLauncher
from so101_demo.runtime.container_campaign.processing_scheduler import ProcessingScheduler
from test_processor_launcher import ATTEMPTS
from test_processor_owner import Fixture


def kill_leftovers(owner):
    """Leave nothing behind whatever the test did: the processor's group and any stray carrying its marker (the registry stays open)."""
    process = owner.process
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    for pid in marker_survivors(owner.root, started_ticks=0):
        if pid > 0:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                pass


def test_a_native_scheduler_processes_through_one_native_processor_and_proves_it_stopped(tmp_path):
    fixture = Fixture(tmp_path)
    run = fixture.paths["run"]
    shutil.rmtree(run / "processing/p00")     # the fixture's own p00/g1 is not this launch's: the launcher makes it
    scope, manifest = run / "scope.json", run / "inputs.json"
    scope.write_text("{}\n")
    manifest.write_text("{}\n")
    for relative in ATTEMPTS:
        (run / relative).mkdir(parents=True, exist_ok=True)
    runtime_ref = json.loads(fixture.spec_path.read_text())["parallel_runtime"]
    fixture.spec_path.unlink()     # the launcher writes the spec of the slot it prepares
    script = SOURCE_ROOT / "test/support/native_processor_world.py"
    launcher = NativeProcessorLauncher(context=fixture.context, paths=fixture.paths, registry=fixture.registry,
        parallel_runtime=runtime_ref, approved_inputs=(), config_paths=(), install_prefix=tmp_path,
        command=[sys.executable, str(script), "--mode", "serve"], base_environment=dict(os.environ))
    admitted = []
    row = dict(scene_id="scene-01", location=str(fixture.attempt), proof=dict(processing="PENDING", result_sha256="a" * 64))
    inputs = {"scene-01": dict(scope=dict(path=str(scope), sha256=hashlib.sha256(scope.read_bytes()).hexdigest()),
                               inputs_manifest=dict(path=str(manifest), sha256=hashlib.sha256(manifest.read_bytes()).hexdigest()))}
    scheduler = ProcessingScheduler(context=fixture.context, runtime=launcher.runtime, config={"processor_count": 4}, root=run,
        launcher=launcher, admit_slots=admitted.append, case_inputs=inputs, max_processors=1)
    try:
        summary = asyncio.run(scheduler.run([row], deadline_s=time.monotonic() + 120.))
    finally:
        for owner in scheduler.owners:
            kill_leftovers(owner)
    assert [slot.worker_id for slot in admitted[0]] == ["p00"] and summary["processors"] == 1
    assert summary["processors_stopped"] is True and summary["launches"] == 1
    scene, = summary["scenes"]
    assert scene["status"] == "FAULT" and scene["fault"] == "PROCESSING_REFUSED" and "PHASE1_RECORD_REFUSED" in scene["reason"]
    journal = [json.loads(line) for line in (run / "host/processing-journal.jsonl").read_text().splitlines()]
    assert [item["event"] for item in journal] == ["phase2_start", "processor_started", "dispatch", "result", "scene_fault",
                                                    "phase2_end"]
    record, = [item for item in fixture.registry.records() if item["launch"]["role"] == "processor"]
    assert record["launch"]["launcher"] == "native" and record["launch"]["launch_id"] == "processing-p00-g1"
    observed = record["exit_inspect"]
    assert observed["kind"] == "native_instance_exit" and observed["group_members"] == [] and observed["marker_survivors"] == []
    assert fixture.registry.role_terminated("processor", lambda cid: None, inspect_native=lambda item: item["exit_inspect"])
    fixture.registry.close()
