"""Phase 2 of the two-phase collection: a queue of phase-1 scenes served by `processor_count` processor containers.

One scene is one task. A task result is classified (the processor's own classification, `act_processor.processing`):

    VALID, INVALID          final; INVALID data (rc 3) is never retried
    REFUSED                 a fault of that scene; not retried
    INFRASTRUCTURE_FAILURE  retried in a new attempt directory `-proc-<n+1>` on any idle processor, up to
                            `processing_max_attempts`; after the last failed attempt the scene is a fault

A processor container that stops answering or fails its task is lost: its in-flight task is an infrastructure failure (it counts as
an attempt) and the processor is replaced by the next launch generation while scenes remain. Everything that happens is appended
and fsynced to `host/processing-journal.jsonl`, one JSON object per line:

    {schema_version, kind: ACT_PROCESSING_JOURNAL, seq, monotonic_s, event, ...fields}

    event            fields
    phase2_start     queue, processors, max_attempts, deadline_s
    processor_started / processor_start_failed / processor_lost / processor_relaunch    processor_id, launch_generation, reason
    dispatch         scene_id, task_id, proc_attempt, processor_id, launch_generation, output_dir
    result           scene_id, task_id, proc_attempt, outcome, retryable, reason, processor_rc
    retry            scene_id, next_attempt, reason
    scene_fault      scene_id, fault (PROCESSING_REFUSED | PROCESSING_RETRIES_EXHAUSTED), reason
    scene_missing    scene_id, reason (PROCESSING_DEADLINE | PROCESSOR_UNAVAILABLE)
    deadline         deadline_s, unprocessed
    phase2_end       counts, processors_stopped

At the phase deadline dispatch stops, the in-flight tasks are ended by terminating their processors, and every scene without a final
result is missing evidence. Processors are terminated and their containers proven stopped before `run` returns.
"""

import asyncio
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.container_campaign.processing_limits import (
    processing_max_attempts, processing_task_timeout_s, processor_count_for, read_mem_available_bytes)
from so101_demo.runtime.container_campaign.service_owner import _write
from so101_demo.runtime.container_campaign.task_contracts import TASK_ID_PATTERN, InputRef, TaskSpec
from so101_demo.runtime.container_campaign.task_control import ContainerTaskControl
from so101_demo.runtime.container_campaign.task_journal import read_container_task_result
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from so101_teleop.unified.worker_slots import ActWorkerSlot

import re

JOURNAL_NAME = "processing-journal.jsonl"
JOURNAL_KIND = "ACT_PROCESSING_JOURNAL"
TASK_KIND = "ACT_PROCESSING_TASK"
RESULT_KIND = "ACT_PROCESSING_TASK_RESULT"
FINAL, FAULT, MISSING = "FINAL", "FAULT", "MISSING"
REFUSED_FAULT, EXHAUSTED_FAULT = "PROCESSING_REFUSED", "PROCESSING_RETRIES_EXHAUSTED"
DEADLINE_REASON, UNAVAILABLE_REASON = "PROCESSING_DEADLINE", "PROCESSOR_UNAVAILABLE"
#: a task that the polled status does not show after this many heartbeat timeouts was never received by the processor
ASSIGN_ACK_HEARTBEATS = 3
_OUTCOMES = ("VALID", "INVALID", "REFUSED", "INFRASTRUCTURE_FAILURE")


class ProcessingJournal:
    """Append-only JSON lines; every line is flushed and fsynced before `append` returns."""

    def __init__(self, path, clock=time.monotonic):
        self.path, self.clock, self._seq, self._lock = Path(path), clock, 0, threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event, **fields):
        with self._lock:
            self._seq += 1
            line = json.dumps(dict(schema_version=1, kind=JOURNAL_KIND, seq=self._seq, monotonic_s=float(self.clock()),
                                   event=event, **fields), sort_keys=True, allow_nan=False) + "\n"
            created = not self.path.exists()
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, line.encode())
                os.fsync(fd)
            finally:
                os.close(fd)
            if created:
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)


class _Worker:
    def __init__(self, slot):
        self.slot, self.generation, self.owner, self.control = slot, 0, None, None

    @property
    def processor_id(self):
        return self.slot.worker_id


class _Lost(Exception):
    """The processor cannot finish the task it holds."""


class _PastDeadline(Exception):
    pass


class ProcessingScheduler:
    def __init__(self, *, context, runtime, config, root, launcher, admit_slots, case_inputs, control_factory=None,
                 clock=time.monotonic, memory_reader=read_mem_available_bytes, max_processors=None):
        """`max_processors` caps the processors whatever the configuration or the memory allow: a native single worker passes 1."""
        if (not callable(launcher) or not callable(admit_slots) or type(case_inputs) is not dict or not callable(clock)
                or max_processors is not None and (type(max_processors) is not int or max_processors < 1)):
            raise ValueError("PROCESSING_SCHEDULER_CONFIG_INVALID")
        self.max_processors = max_processors
        self.context, self.runtime, self.config, self.root = context, runtime, config, Path(root)
        self.launcher, self.admit_slots, self.case_inputs = launcher, admit_slots, case_inputs
        self.control_factory = control_factory or (lambda owner: ContainerTaskControl(owner=owner))
        self.clock, self.memory_reader = clock, memory_reader
        self.owners = []          # every launched processor owner, every generation (the campaign owner closes what is left)
        self.stop_state = {}      # launch id -> whether that processor container's stop was proven, every generation
        self.journal = ProcessingJournal(self.root / "host" / JOURNAL_NAME, clock)
        self.max_attempts = processing_max_attempts(config)

    # ---- the run -----------------------------------------------------------------------------------------------------------

    async def run(self, rows, *, deadline_s):
        """Process every scene of `rows` (verified phase-1 rows with `proof.processing == PENDING`); returns the summary."""
        items = [self._item(row) for row in rows]
        if not items or len({item["scene_id"] for item in items}) != len(items):
            raise ValueError("PROCESSING_QUEUE_INVALID")
        self.deadline_s = float(deadline_s)
        count = processor_count_for(self.config, queue_length=len(items), available_bytes=self._available_bytes())
        if self.max_processors is not None:
            count = min(count, self.max_processors)
        slots = tuple(ActWorkerSlot(self.context.campaign_id, f"p{index:02d}", self.context.execution_generation)
                      for index in range(count))
        self.admit_slots(slots)
        self.items = {item["scene_id"]: item for item in items}
        self.queue = deque(item["scene_id"] for item in items)
        self.inflight = 0
        self.state = {}            # scene_id -> dict(status, outcome, reason, attempts, output_dir)
        self._changed = asyncio.Event()
        self.journal.append("phase2_start", queue=[item["scene_id"] for item in items], processors=count,
                            max_attempts=self.max_attempts, deadline_s=self.deadline_s)
        workers = [_Worker(slot) for slot in slots]
        try:
            await asyncio.gather(*(self._serve(worker) for worker in workers))
        finally:
            stopped = await self._stop_all(workers)
        return self._summary(workers, stopped)

    def _available_bytes(self):
        try:
            return self.memory_reader()
        except (OSError, ValueError):
            return 0   # unknown memory: the smallest default (one processor), never an invented larger one

    def _item(self, row):
        scene = row["scene_id"]
        proof = row["proof"]
        refs = self.case_inputs[scene]
        sealed = Path(row["location"])
        if any(re.fullmatch(TASK_ID_PATTERN, f"{scene}-proc-{n}") is None for n in range(1, self.max_attempts + 1)):
            raise ValueError("PROCESSING_TASK_ID_INVALID")
        return dict(scene_id=scene, phase1_attempt=str(sealed), attempt_name=sealed.parent.name, made=0,
                    phase1_result_sha256=proof["result_sha256"], inputs_manifest=dict(refs["inputs_manifest"]),
                    scope=dict(refs["scope"]), attempt=1)

    # ---- one processor -----------------------------------------------------------------------------------------------------

    async def _serve(self, worker):
        if not await self._launch(worker):
            self._pulse()
            return
        while True:
            if self.clock() >= self.deadline_s:
                break
            if not self.queue:
                if self.inflight == 0:
                    break
                await self._wait_changed()
                continue
            scene = self.queue.popleft()
            self.inflight += 1
            try:
                alive = await self._process(worker, scene)
            finally:
                self.inflight -= 1
                self._pulse()
            if not alive and (not self.queue or self.clock() >= self.deadline_s or not await self._replace(worker)):
                break
        self._pulse()

    async def _launch(self, worker):
        """Start the next launch generation of this slot; up to `processing_max_attempts` consecutive failures."""
        for _ in range(self.max_attempts):
            worker.generation += 1
            owner = control = None
            try:
                owner = self.launcher(slot=worker.slot, generation=worker.generation)
                self.owners.append(owner)
                control = self.control_factory(owner)
                worker.owner, worker.control = owner, control
                await control.start()
            except Exception as error:   # noqa: BLE001 - recorded; the next generation may start
                self.journal.append("processor_start_failed", processor_id=worker.processor_id,
                                    launch_generation=worker.generation, reason=_why(error))
                await self._terminate(worker)
                worker.owner = worker.control = None
                continue
            self.journal.append("processor_started", processor_id=worker.processor_id, launch_generation=worker.generation)
            return True
        return False

    async def _replace(self, worker):
        stopped = await self._terminate(worker)
        worker.owner = worker.control = None
        self.journal.append("processor_relaunch", processor_id=worker.processor_id, launch_generation=worker.generation + 1,
                            previous_stopped=stopped)
        return await self._launch(worker)

    async def _terminate(self, worker):
        """Terminate this processor; True once its container is proven stopped. Never raises."""
        control = worker.control
        if control is None:
            return True
        launch_id = getattr(getattr(worker.owner, "launch", None), "launch_id", None)
        try:
            status = await control.terminate("PROCESSING_END")
            proven = bool(status.resources_released)
        except Exception:   # noqa: BLE001
            proven = False
        if launch_id is not None:
            self.stop_state[launch_id] = proven      # the latest word on this container: a retry may prove it
        return proven

    async def _stop_all(self, workers):
        results = await asyncio.gather(*(self._terminate(worker) for worker in workers))
        # every generation of every slot, not only the last one: a replaced container that was never proven stopped still counts
        return all(results) and all(self.stop_state.values())

    # ---- one task ----------------------------------------------------------------------------------------------------------

    async def _process(self, worker, scene):
        """Run the scene's next attempt on this processor. Returns False when the processor was lost."""
        item = self.items[scene]
        attempt = item["attempt"]
        try:
            result = await self._run_task(worker, item)
        except _PastDeadline:
            self._missing(scene, DEADLINE_REASON)
            return True
        except _Lost as error:
            self.journal.append("processor_lost", processor_id=worker.processor_id, launch_generation=worker.generation,
                                reason=str(error)[:300], scene_id=scene)
            self._infrastructure_failure(scene, attempt, str(error))
            return False
        outcome = result["outcome"]
        if outcome in ("VALID", "INVALID"):
            self.state[scene] = dict(status=FINAL, outcome=outcome, reason=result.get("reason"), attempts=attempt,
                                     output_dir=result.get("output_dir"), processed_result=result.get("processed_result"))
        elif outcome == "REFUSED":
            self._fault(scene, attempt, REFUSED_FAULT, result.get("reason"))
        else:
            self._infrastructure_failure(scene, attempt, result.get("reason") or "INFRASTRUCTURE_FAILURE")
        return True

    def _infrastructure_failure(self, scene, attempt, reason):
        if self.clock() >= self.deadline_s:
            self._missing(scene, DEADLINE_REASON)
        elif attempt < self.max_attempts:
            self.items[scene]["attempt"] = attempt + 1
            self.journal.append("retry", scene_id=scene, next_attempt=attempt + 1, reason=str(reason)[:300])
            self.queue.appendleft(scene)
        else:
            self._fault(scene, attempt, EXHAUSTED_FAULT, reason)

    def _fault(self, scene, attempt, fault, reason):
        self.state[scene] = dict(status=FAULT, fault=fault, reason=None if reason is None else str(reason)[:300],
                                 attempts=attempt)
        self.journal.append("scene_fault", scene_id=scene, fault=fault, reason=self.state[scene]["reason"])

    def _missing(self, scene, reason):
        self.state[scene] = dict(status=MISSING, reason=reason, attempts=self.items[scene]["made"])
        self.journal.append("scene_missing", scene_id=scene, reason=reason)

    def _task_spec(self, worker, item):
        scene, attempt = item["scene_id"], item["attempt"]
        task_id = f"{scene}-proc-{attempt}"
        output = self.root / "processing" / scene / f"{item['attempt_name']}-proc-{attempt}"
        document = dict(schema_version=1, kind=TASK_KIND, task_id=task_id, processor_id=worker.processor_id,
                        launch_generation=worker.generation, scene_id=scene, proc_attempt=attempt,
                        phase1_attempt=item["phase1_attempt"], phase1_result_sha256=item["phase1_result_sha256"],
                        inputs_manifest=item["inputs_manifest"], scope=item["scope"], output_dir=str(output))
        path = Path(worker.owner.launch.owned_root) / "task-inputs" / (task_id + ".json")
        _write(path, document)
        digest = hashlib.sha256(canonical_json(document) + b"\n").hexdigest()
        budget = processing_task_timeout_s(self.config)   # its own key: the Teacher stage limits are not a processing budget
        deadline = min(self.clock() + budget, self.deadline_s, self.context.deadline_monotonic_s)
        return TaskSpec(task_id=task_id, inputs_ref=InputRef(path=str(path), sha256=digest), deadline_monotonic_s=deadline), output

    async def _run_task(self, worker, item):
        """Assign one task and wait for its result. Raises `_Lost` or `_PastDeadline`."""
        task, output = await asyncio.to_thread(self._task_spec, worker, item)
        control, runtime = worker.control, self.runtime
        item["made"] += 1
        self.journal.append("dispatch", scene_id=item["scene_id"], task_id=task.task_id, proc_attempt=item["attempt"],
                            processor_id=worker.processor_id, launch_generation=worker.generation, output_dir=str(output))
        try:
            await control.assign_task(task)
        except Exception:   # noqa: BLE001 - an uncertain exchange is only ever queried, never repeated
            pass
        last_ok = assigned_at = self.clock()
        backstop = task.deadline_monotonic_s + runtime.heartbeat_timeout_s
        acknowledgement_s = ASSIGN_ACK_HEARTBEATS * runtime.heartbeat_timeout_s
        acknowledged = False
        while True:
            if self.clock() >= self.deadline_s:
                raise _PastDeadline
            try:
                status = await asyncio.wait_for(control.get_status(task.task_id), runtime.heartbeat_timeout_s)
                last_ok = self.clock()
            except Exception as error:   # noqa: BLE001
                if self.clock() - last_ok >= runtime.heartbeat_timeout_s:
                    raise _Lost("PROCESSOR_UNREACHABLE: " + _why(error)) from error
                await asyncio.sleep(runtime.heartbeat_interval_s)
                continue
            seen = status.task
            if seen is not None and seen.task_id == task.task_id and seen.state == "SUCCEEDED":
                return await self._collect(worker, task, item)
            if (seen is not None and seen.task_id == task.task_id and seen.state == "FAILED") or status.state in (
                    "STOPPING", "TERMINATED") or status.fault_reason:
                reason = (seen.fault_reason if seen is not None and seen.fault_reason else status.fault_reason or status.state)
                raise _Lost("PROCESSOR_TASK_FAILED: " + str(reason))
            acknowledged = acknowledged or (seen is not None and seen.task_id == task.task_id)
            if not acknowledged and self.clock() - assigned_at >= acknowledgement_s:
                # an assignment that was lost on the way is not repeated (it might run twice); the processor is replaced instead of
                # waiting out the task budget
                raise _Lost("PROCESSOR_ASSIGN_NOT_ACKNOWLEDGED")
            if self.clock() >= backstop:
                raise _Lost("PROCESSOR_TASK_DEADLINE_EXCEEDED")
            await asyncio.sleep(runtime.heartbeat_interval_s)

    async def _collect(self, worker, task, item):
        try:
            record = await asyncio.to_thread(read_container_task_result, worker.owner.launch.owned_root, task_id=task.task_id)
        except ValueError as error:
            raise _Lost("PROCESSING_RESULT_UNREADABLE: " + _why(error)) from error
        result = record["result"]
        if (result.get("kind") != RESULT_KIND or result.get("task_id") != task.task_id
                or result.get("proc_attempt") != item["attempt"] or result.get("outcome") not in _OUTCOMES):
            result = dict(outcome="INFRASTRUCTURE_FAILURE", retryable=True, reason="PROCESSING_RESULT_INVALID", processor_rc=None)
        self.journal.append("result", scene_id=item["scene_id"], task_id=task.task_id, proc_attempt=item["attempt"],
                            outcome=result["outcome"], retryable=result["outcome"] == "INFRASTRUCTURE_FAILURE",
                            reason=result.get("reason"), processor_rc=result.get("processor_rc"),
                            task_result_sha256=record["task_result_sha256"])
        # the instance is idle again once the executor has published the result; refresh the adapter's view before the next task
        for _ in range(20):
            try:
                if (await worker.control.get_status()).state != "BUSY":
                    break
            except Exception:   # noqa: BLE001
                break
            await asyncio.sleep(self.runtime.heartbeat_interval_s)
        return result

    # ---- waiting and the summary -------------------------------------------------------------------------------------------

    def _pulse(self):
        changed, self._changed = self._changed, asyncio.Event()
        changed.set()

    async def _wait_changed(self):
        try:
            await asyncio.wait_for(self._changed.wait(), self.runtime.heartbeat_interval_s)
        except asyncio.TimeoutError:
            pass

    def _summary(self, workers, stopped):
        unprocessed = [scene for scene in self.items if scene not in self.state]
        if unprocessed:
            reason = DEADLINE_REASON if self.clock() >= self.deadline_s else UNAVAILABLE_REASON
            if reason == DEADLINE_REASON:
                self.journal.append("deadline", deadline_s=self.deadline_s, unprocessed=unprocessed)
            for scene in unprocessed:
                self._missing(scene, reason)
        scenes = [dict(scene_id=scene, **self.state[scene]) for scene in self.items]
        counts = {name: sum(1 for item in scenes if item.get("outcome") == name or item["status"] == name)
                  for name in ("VALID", "INVALID", FAULT, MISSING)}
        self.journal.append("phase2_end", counts=counts, processors_stopped=stopped)
        return dict(schema_version=1, kind="act_collection_processing_summary", campaign_id=self.context.campaign_id,
                    processors=len(workers), max_attempts=self.max_attempts, deadline_s=self.deadline_s,
                    processors_stopped=stopped, launches=len(self.owners), counts=counts, scenes=scenes,
                    journal=str(self.journal.path))


def _why(error):
    return ((str(error) or type(error).__name__)[:300])
