"""One parallel rollout run: the policy service, the waves of shards, the INVALID re-queue, the proofs and the results.

The owner is the rollout's counterpart of `ContainerCampaignOwner`. It does not use the unified admission (a rollout has none: like
the native command it proves its own preconditions, `cli/act_rollout_parallel.py`), but it keeps what makes a parallel run safe:

- the policy service is started first and stopped last, with its own process identity and stop proof;
- every wave launches fresh shards, waits for all of them to be READY (the coordinator's barrier), assigns one task at a time per
  shard under the `RecordingGate`, and ends only when every container of the wave has exited and been inspected again;
- a unit whose attempt is INVALID (a verdict of the episode, or a faulted task) is queued again in a later wave, on fresh shards,
  up to `max_invalid_retries` more attempts; units that cannot run because the run stopped are reported as `NOT_RUN`;
- at the end the containers are receipted (logs saved, containers removed, absence proven) and the results are written.

A fault that is not the fault of one task (a shard that did not start, a wave that could not be proven stopped, a policy service
that is gone) stops the dispatch; what was proven is kept and the run exits non-zero.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time

from so101_demo.act.service_telemetry import sample_from_row, summarize_service
from so101_demo.runtime.act_rollout import aggregate
from so101_demo.runtime.container_campaign import container_receipts, stage_records
from so101_demo.runtime.container_campaign.service_owner import _write

EXIT_OK, EXIT_INVALID, EXIT_REFUSED, EXIT_STOP_UNCONFIRMED, EXIT_START_FAILED = 0, 1, 2, 3, 4
#: the policy service faulted (or answered a run of errors) while the run was going: dispatch stopped, and what ran is kept
EXIT_POLICY_FAULT = 5
#: anything else that went wrong after the run directory existed (2 is for a refusal before anything started)
EXIT_RUN_FAULT = 6
STAGE = "rollout"


class RolloutRunFault(RuntimeError):
    """The run cannot go on; `code` is the first cause."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _line(row):
    return json.dumps(row, sort_keys=True) + "\n"


class RolloutCampaignOwner:
    def __init__(self, *, context, run, registry, launcher, coordinator_factory, policy, units, rollout, options,
                 docker_runner, inspect_container, clock=time.monotonic, sleep=asyncio.sleep, gpu_check=None,
                 monitor_interval_s=1.0):
        self.context, self.run_root, self.registry = context, Path(run), registry
        self.launcher, self.coordinator_factory, self.policy = launcher, coordinator_factory, policy
        self.units, self.rollout, self.options = list(units), rollout, options
        self.docker_runner, self.inspect_container = docker_runner, inspect_container
        self.clock, self.sleep, self.gpu_check = clock, sleep, gpu_check
        self.monitor_interval_s = monitor_interval_s
        self.host = self.run_root / "host"
        self.points = list(dict.fromkeys(unit.point_id for unit in self.units))
        self.group = self.units[0].group
        self.attempts = {}              # (point, trial) -> [attempt records]
        self.waves, self.shards = [], []
        self.dispatch_stopped = None
        self.fault = None
        self.exit_code = EXIT_OK
        self.policy_ready = None
        self._started = self.clock()
        self._cleanup = None
        self.not_run = []
        self.policy_fault = None
        self.service_samples = []

    # ---- dispatch ----------------------------------------------------------------------------------------------------------

    def stop_dispatch(self, reason):
        if self.dispatch_stopped is None:
            self.dispatch_stopped = reason

    def dispatch_allowed(self):
        return self.dispatch_stopped is None and self.clock() < self.context.deadline_monotonic_s

    async def _monitor(self):
        """Once a second: the policy service is the process that was proved and answers, and the campaign deadline holds."""
        try:
            while True:
                if self.clock() >= self.context.deadline_monotonic_s:
                    self.stop_dispatch("ROLLOUT_CAMPAIGN_DEADLINE_EXPIRED")
                elif not await asyncio.to_thread(self.policy.healthy):
                    reason = getattr(self.policy, "unhealthy_reason", None) or "HEALTH_CHECK_FAILED"
                    self.policy_fault = self.policy_fault or f"ROLLOUT_POLICY_SERVICE_UNHEALTHY: {reason}"[:300]
                    self.stop_dispatch("ROLLOUT_POLICY_SERVICE_UNHEALTHY")
                await self.sleep(self.monitor_interval_s)
        except asyncio.CancelledError:
            raise

    # ---- the run -----------------------------------------------------------------------------------------------------------

    async def run(self):
        monitor = None
        try:
            try:
                self.policy_ready = await asyncio.to_thread(self.policy.start)
                if self.gpu_check is not None:
                    await asyncio.to_thread(self.gpu_check, self.policy)
            except Exception as error:      # noqa: BLE001 - nothing else was started
                self.exit_code = EXIT_START_FAILED
                self.fault = f"POLICY_SERVICE_START_FAILED: {type(error).__name__}: {error}"[:300]
                return
            monitor = asyncio.create_task(self._monitor())
            await self._waves()
        except RolloutRunFault as fault:
            self.fault = self.fault or fault.code
        except Exception as error:      # noqa: BLE001 - reported after the stop proofs
            self.fault = self.fault or f"{type(error).__name__}: {error}"[:300]
            self.stop_dispatch("ROLLOUT_RUN_FAULT")
        finally:
            if monitor is not None:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)

    async def _waves(self):
        pending = list(self.units)
        self.not_run = list(pending)
        wave = 0
        while pending:
            if not self.dispatch_allowed():
                break
            if self.gpu_check is not None:
                # nobody else may have taken the GPU since the last wave
                await asyncio.to_thread(self.gpu_check, self.policy)
            count = min(self.options.shards, len(pending))
            worker_ids = tuple(f"w{index:02d}" for index in range(count))
            context = replace(self.context, worker_count=count)
            by_id = {unit.unit_id: unit for unit in pending}
            plan = dict(wave_index=wave, scene_ids=[unit.unit_id for unit in pending], assignment=None)
            coordinator = self.coordinator_factory(context=context, units=by_id)
            shards = self.launcher(plan=plan, worker_ids=worker_ids, context=context)
            self.shards.extend(shards)
            started = self.clock()
            try:
                outcome = await coordinator.run_wave(plan=plan, shards=shards, endpoints={},
                                                     dispatch_allowed=self.dispatch_allowed)
            except Exception as error:      # noqa: BLE001 - the wave's containers are stopped and proven below
                outcome = None
                self.fault = self.fault or f"ROLLOUT_WAVE_FAILED: {type(error).__name__}: {error}"[:300]
                self.stop_dispatch("ROLLOUT_WAVE_FAILED")
                self.exit_code = EXIT_START_FAILED if wave == 0 and not self.attempts else self.exit_code
            cleanup = await asyncio.gather(*(shard.close() for shard in shards))
            if any(value["terminated"] is not True for value in cleanup):
                self.stop_dispatch("ROLLOUT_SHARD_STOP_UNCONFIRMED")
                raise RolloutRunFault("ROLLOUT_SHARD_STOP_UNCONFIRMED")
            if outcome is None:
                break
            coordinator.complete_wave_cleanup(plan, shards)
            records = await asyncio.to_thread(self._verify_wave, wave, plan, outcome, shards, coordinator, by_id)
            _write(self.host / f"wave-{wave}-verified.json", dict(
                schema_version=1, kind="ACT_ROLLOUT_WAVE_VERIFIED", wave_index=wave, shards=count,
                wall_s=round(self.clock() - started, 3), infra_errors=outcome["infra_errors"], units=records))
            self.waves.append(dict(wave_index=wave, shards=count, units=[record["unit_id"] for record in records],
                                   wall_s=round(self.clock() - started, 3)))
            pending = self._settle_wave(records, by_id)
            self.not_run = list(pending)
            if (self.dispatch_stopped is None and not outcome["infra_errors"]
                    and all(record["state"] == "NOT_RUN" for record in records)):
                self.stop_dispatch("ROLLOUT_WAVE_MADE_NO_PROGRESS")        # never queue the same units again and again
                self.fault = self.fault or "ROLLOUT_WAVE_MADE_NO_PROGRESS"
            if outcome["infra_errors"]:
                self.stop_dispatch("ROLLOUT_INSTANCE_EXECUTION_FAULT")
                self.fault = self.fault or "ROLLOUT_INSTANCE_EXECUTION_FAULT: " + json.dumps(outcome["infra_errors"][:3])[:250]
            wave += 1

    # ---- verification ------------------------------------------------------------------------------------------------------

    def _verify_wave(self, wave, plan, outcome, shards, coordinator, by_id):
        """One record per unit of the wave: collected and verified, faulted, or never run. Reads the journal and the files."""
        journal = coordinator.waves[wave]
        records = journal.records()
        faults = {item["scene_id"]: item for item in outcome.get("scene_faults", ())}
        rows = {row["scene_id"]: row for row in outcome["case_results"]}
        verified = []
        for unit_id in plan["scene_ids"]:
            unit = by_id[unit_id]
            base = dict(unit_id=unit_id, point_id=unit.point_id, trial=unit.trial, attempt_number=unit.attempt_number,
                        wave_index=wave)
            row = rows.get(unit_id)
            if row is None:
                fault = faults.get(unit_id)
                state = "FAULT" if fault is not None else "NOT_RUN"
                verified.append(dict(base, state=state, verdict="INVALID" if fault is not None else None,
                                     reason=None if fault is None else fault["reason"]))
                continue
            record = records[row["task_id"]]["collected"]
            try:
                checked = self._check_collected(unit, row, record)
                self.service_samples.extend(checked.pop("service_samples"))       # kept in memory, not in the wave record
                verified.append(dict(base, **checked))
            except (OSError, ValueError, KeyError, TypeError) as error:
                verified.append(dict(base, state="FAULT", verdict="INVALID",
                                     reason=f"ROLLOUT_RESULT_UNVERIFIED: {type(error).__name__}: {error}"[:300]))
        return verified

    def _check_collected(self, unit, row, record):
        result = record["result"]
        task_dir = Path(row["location"])
        if (result.get("kind") != "ACT_CONTAINER_ROLLOUT_TASK_RESULT" or result["task_id"] != row["task_id"]
                or result["scene_id"] != unit.unit_id or result["point_id"] != unit.point_id
                or result["trial"] != unit.trial or result["attempt_number"] != unit.attempt_number
                or result["attempt_id"] != unit.unit_id or result["group"] != unit.group):
            raise ValueError("task result does not describe this unit")
        evidence = []
        for relative in result["evidence"]:
            path = task_dir / relative
            if path.is_symlink() or not path.is_file() or ".." in Path(relative).parts:
                raise ValueError("evidence file missing: " + relative)
            raw = path.read_bytes()
            evidence.append(dict(path=str(path.relative_to(self.run_root)), sha256=_sha256(raw), bytes=len(raw)))
        episode = json.loads((task_dir / "episode" / "episode.json").read_bytes())
        if (episode["verdict"] != result["verdict"] or episode["attempt_id"] != unit.unit_id
                or episode["run_id"] != self.rollout["run_id"] or episode["kind"] != "ACT_ROLLOUT_EPISODE"):
            raise ValueError("episode.json does not match the task result")
        motion = (episode.get("result") or {}).get("motion") or {}
        return dict(state="COLLECTED", verdict=result["verdict"], reason=result["reason"], done=result["done"],
                    task_id=row["task_id"], worker_id=row["worker_id"], launch_id=row["launch_id"],
                    task_dir=str(task_dir.relative_to(self.run_root)), task_result_sha256=record["task_result_sha256"],
                    elapsed_wall_s=result["elapsed_wall_s"], task_wall_s=result["task_wall_s"], counts=result["counts"],
                    clamped_steps=result["clamped_steps"], stop_confirmed=result["stop_confirmed"],
                    retire_errors=result["retire_errors"], goal_response=result.get("goal_response"),
                    max_arm_displacement_rad=motion.get("max_arm_displacement_rad"), evidence=evidence,
                    service=result.get("service"), service_samples=self._service_samples(task_dir))

    def _service_samples(self, task_dir):
        """One sample per step row that carries the policy service's account: the outcome, the queue wait, the model time and
        the client's round trip (the run's statistics are computed from these, not from the episodes' statistics)."""
        samples = []
        steps = Path(task_dir) / "episode" / "steps.jsonl"
        if steps.is_file():
            for line in steps.read_text().splitlines():
                if '"service"' in line:
                    sample = sample_from_row(json.loads(line))
                    if sample is not None:
                        samples.append(sample)
        return samples

    def _settle_wave(self, records, by_id):
        """Record each attempt; the units to run again are the INVALID ones with attempts left."""
        again = []
        group_root = self.run_root / self.group
        group_root.mkdir(mode=0o700, exist_ok=True)
        for record in records:
            unit = by_id[record["unit_id"]]
            if record["state"] == "NOT_RUN":
                continue
            attempt = {name: record[name] for name in record if name not in ("point_id", "trial", "state")}
            attempt["state"] = record["state"]
            self.attempts.setdefault(unit.key, []).append(attempt)
            evidence = [item["path"] for item in record.get("evidence", ())]
            if record["verdict"] == "INVALID":
                with (group_root / "invalid-runs.jsonl").open("a") as handle:
                    handle.write(_line({"scene_id": unit.point_id, "attempt_id": unit.unit_id, "reason": record["reason"],
                                        "evidence": evidence}))
                if unit.attempt_number <= self.options.max_invalid_retries:
                    again.append(unit.retry())
            else:
                with (group_root / "act-runs.jsonl").open("a") as handle:
                    handle.write(_line({"search_locked": True, "done": record["done"], "interventions": 0,
                                        "elapsed_wall_s": record["elapsed_wall_s"], "scene_id": unit.point_id,
                                        "evidence": evidence}))
        # a unit that did not run stays queued, and so does a retry: if the run stops, they are reported as not run
        not_run = [by_id[record["unit_id"]] for record in records if record["state"] == "NOT_RUN"]
        return again + not_run

    # ---- close and results -------------------------------------------------------------------------------------------------

    async def close(self):
        """Stop what is still running, prove every stop, receipt the containers and write the cleanup record."""
        if self._cleanup is not None:
            return self._cleanup
        self.stop_dispatch("ROLLOUT_CLOSING")
        shards = await asyncio.gather(*(shard.close() for shard in self.shards), return_exceptions=True)
        policy = await asyncio.to_thread(self.policy.stop)
        # a run that never launched a shard has nothing to re-prove (the registry answers False for no launch at all)
        containers_clear = (not self.shards) or await asyncio.to_thread(self.registry.all_terminated, self.inspect_container)
        shards_clear = all(isinstance(value, dict) and value.get("terminated") is True for value in shards)
        receipt = None
        if containers_clear and shards_clear and self.shards:
            receipt = await asyncio.to_thread(self._receipt)
        result = dict(terminated=bool(containers_clear and shards_clear and policy["confirmed"] is True),
                      shards=[value if isinstance(value, dict) else dict(error_type=type(value).__name__, reason=str(value))
                              for value in shards],
                      containers_independently_clear=containers_clear, policy_service=policy, receipt=receipt,
                      stop_reason=self.dispatch_stopped)
        _write(self.host / "campaign-cleanup.json", result)
        self._cleanup = result
        return result

    def _receipt(self):
        """`containers-receipt-01-rollout.json`, or the error that left the containers standing for inspection."""
        try:
            records = self.registry.records()
            record = stage_records.write_record(self.host, STAGE, dict(
                run_id=self.rollout["run_id"], waves=len(self.waves), units=len(self.units),
                run_identity_sha256=self.rollout["run_identity_sha256"],
                policy_stop_proof_sha256=(self.policy.stop_result or {}).get("stop_proof_sha256")))
            written = container_receipts.seal_stage_containers(
                self.host, STAGE, records=records, live_document=lambda item: self.inspect_container(item["owner"]["container_id"]),
                prove_terminated=self.registry.prove_terminated, runner=self.docker_runner,
                stage_record_sha256=record["sha256"])
            return f"containers-receipt-{written['seq']:02d}-{STAGE}.json"
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
            return "ERROR " + type(error).__name__ + ": " + str(error)[:300]

    def finish(self, cleanup, *, header):
        """Write summary.json and table.md; return the run's summary and exit code."""
        trials = max(unit.trial for unit in self.units)
        retry_not_run = frozenset(unit.key for unit in self.not_run if unit.attempt_number > 1)
        summary = aggregate.build_summary(run_id=self.rollout["run_id"], group=self.group, points=self.points, trials=trials,
                                          attempts=self.attempts, retry_not_run=retry_not_run, header=dict(
                                              header, waves=self.waves, policy_service=self._policy_header(),
                                              service=summarize_service(self.service_samples),
                                              policy_fault=self.policy_fault,
                                              cleanup_terminated=cleanup["terminated"], fault=self.fault,
                                              dispatch_stopped=self.dispatch_stopped,
                                              wall_s=round(self.clock() - self._started, 3)))
        totals = summary["totals"]
        if self.policy_fault is not None and self.exit_code in (EXIT_OK, EXIT_START_FAILED):
            self.exit_code = EXIT_POLICY_FAULT              # a service that faulted says more than the wave it fenced
        if self.exit_code == EXIT_OK:
            if self.fault is not None:
                self.exit_code = EXIT_RUN_FAULT
            elif totals["invalid_exhausted"] or totals["not_run"] or totals["retry_not_run"]:
                self.exit_code = EXIT_INVALID
        if not cleanup["terminated"] or (cleanup["receipt"] or "").startswith("ERROR"):
            self.exit_code = EXIT_STOP_UNCONFIRMED
        summary["exit_code"] = self.exit_code
        (self.run_root / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=1) + "\n")
        (self.run_root / "table.md").write_text(aggregate.render_table(summary))
        return summary

    def _policy_header(self):
        stop = self.policy.stop_result or {}
        return dict(ready=self.policy_ready, stop_confirmed=stop.get("confirmed"), stop_proof_sha256=stop.get("stop_proof_sha256"))
