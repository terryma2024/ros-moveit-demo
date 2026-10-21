"""Time limits and sizing of the two-phase collection (design "Time limits").

All times are Host monotonic seconds, the unit of `AdmittedCampaignContext.deadline_monotonic_s`.

    total       the admitted `batch_hard_timeout_s` deadline, covering both phases
    phase 1     ends at the earlier of its own limit and the total:
                  `collect_timeout_s` from admission, if set;
                  otherwise total minus the time phase 2 must keep: `process_timeout_s` if set, else `processing_reserve_s`
    phase 2     starts when the last phase-1 shard is proven stopped and ends at the earlier of `process_timeout_s` from that
                start (if set) and the total minus `verification_reserve_s` (default 600): the Host's independent readback of the
                processed results (it recomputes the QC of every VALID scene and never trusts the processor's memo) runs after
                phase 2 and needs that time before the total

`collect_timeout_s + process_timeout_s` may not exceed the total, and neither may any of the three single values.
"""

from so101_demo.runtime.inference.config import RUNTIME_DOCUMENT_KEYS

DEFAULT_RESERVE_S = 1800
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_VERIFICATION_RESERVE_S = 600
#: one processing task: the offline processor (1200 s) plus its seal margin and the
#: task-result publication; the config key `processing_task_timeout_s` may not be lower (`runtime.inference.config`)
DEFAULT_TASK_TIMEOUT_S = 1800
MAX_DEFAULT_PROCESSORS = 12
#: the processor peaks at 2.2 GiB and its QC child runs after it
PROCESSOR_MEMORY_BYTES = 3 * 2**30


def effective_limits(config, document=None):
    """The campaign config with the keys of the run's runtime document laid over it (a version 1 config may still carry them).

    A key named in both is refused: which value a run used must not depend on an overlay order. No document returns the config."""
    if document is None:
        return config
    keys = [name for name in RUNTIME_DOCUMENT_KEYS if name in document]
    if any(name in config for name in keys):
        raise ValueError("CAMPAIGN_RUNTIME_KEY_CONFLICT")
    return {**config, **{name: document[name] for name in keys}}


def effective_batch_total_s(config, runtime_batch_hard_timeout_s):
    """The campaign total and where it came from: the campaign limits' `batch_hard_timeout_s` when present, else the runtime yaml's."""
    if "batch_hard_timeout_s" in config:
        return config["batch_hard_timeout_s"], "campaign config"
    return runtime_batch_hard_timeout_s, "runtime yaml"


def check_phase_limits(config, batch_hard_timeout_s):
    """Refuse limits that cannot fit the admitted total. `config` is the campaign config (absent keys are not limits)."""
    collect, process = config.get("collect_timeout_s"), config.get("process_timeout_s")
    reserve = config.get("processing_reserve_s")
    verification = config.get("verification_reserve_s")
    if ((verification is not None and verification >= batch_hard_timeout_s)
            or any(value is not None and value > batch_hard_timeout_s for value in (collect, process))
            or (collect is not None and process is not None and collect + process > batch_hard_timeout_s)
            or (reserve is not None and reserve >= batch_hard_timeout_s)):
        raise ValueError("CAMPAIGN_PHASE_LIMITS_EXCEED_TOTAL")


def phase1_deadline_s(config, *, admitted_s, total_deadline_s):
    """When phase-1 dispatch stops (never later than the total)."""
    collect = config.get("collect_timeout_s")
    if collect is not None:
        return min(admitted_s + collect, total_deadline_s)
    kept = config.get("process_timeout_s", config.get("processing_reserve_s", DEFAULT_RESERVE_S))
    return min(total_deadline_s - kept, total_deadline_s)


def phase2_deadline_s(config, *, phase2_start_s, total_deadline_s):
    """When phase-2 dispatch stops and in-flight processing is terminated."""
    process = config.get("process_timeout_s")
    end = total_deadline_s - config.get("verification_reserve_s", DEFAULT_VERIFICATION_RESERVE_S)
    return end if process is None else min(phase2_start_s + process, end)


def processing_task_timeout_s(config):
    """The time budget of one processing task (never the Teacher stage limits), before the phase deadline caps it."""
    return config.get("processing_task_timeout_s", DEFAULT_TASK_TIMEOUT_S)


#: a retry round's sync when round 0 observed none
DEFAULT_RETRY_SYNC_S = 60.0
#: the largest wave `plan_campaign_waves` builds by default
RETRY_MAX_WAVE_SIZE = 20


def retry_invalid_max_rounds(config):
    """How many retry rounds the campaign may run (absent means 0, today's behaviour)."""
    return config.get("retry_invalid_max_rounds", 0)


def retry_round_plan(config, *, now_s, total_deadline_s, scene_count, worker_count, processor_count, observed, runtime):
    """Whether one more retry round (`scene_count` candidates) fits before the total minus `verification_reserve_s`.

    `observed` holds round-0 measurements, each optional: `wave_wall_s` (wall seconds per wave), `sync_s`, `task_s` (seconds per
    processing task) and `processor_start_s`. `runtime` holds the parallel-runtime hard timeouts used when nothing was observed.
    `collect_timeout_s` does not apply to retry rounds. `worker_count` is the shard slot count (waves are packed by
    `plan_campaign_waves`' rule, at most `RETRY_MAX_WAVE_SIZE` scenes per wave)."""
    waves = -(-scene_count // RETRY_MAX_WAVE_SIZE)
    wave_s = max(observed.get("wave_wall_s") or (), default=None)
    if wave_s is None:
        concurrency = max(1, min(worker_count, config.get('max_concurrent_recordings', worker_count),
                                 config.get('max_tasks_in_flight', worker_count)))
        task_s = (runtime['executing_hard_timeout_s'] + runtime['finalizing_hard_timeout_s']
                  + runtime['worker_recovery_timeout_s'] + runtime['initializing_hard_timeout_s'])
        wave_times = []
        for offset in range(0, scene_count, RETRY_MAX_WAVE_SIZE):
            count = min(RETRY_MAX_WAVE_SIZE, scene_count - offset)
            batches_s = task_s * -(-count // concurrency)
            spaced_s = config.get('min_assignment_gap_s', 0) * (count - 1) + task_s
            wave_times.append(runtime['initializing_hard_timeout_s'] + max(batches_s, spaced_s))
        recording_s = sum(wave_times)
        wave_s = max(wave_times, default=0)
    else:
        recording_s = wave_s * waves
    sync_s = observed.get("sync_s")
    sync_s = DEFAULT_RETRY_SYNC_S if sync_s is None else sync_s
    task_s = max(observed.get("task_s") or (), default=None)
    task_s = processing_task_timeout_s(config) if task_s is None else task_s
    start_s = max(observed.get("processor_start_s") or (), default=None)
    start_s = runtime['initializing_hard_timeout_s'] if start_s is None else start_s
    processing_s = task_s * -(-scene_count // max(1, processor_count)) + start_s
    end_s = total_deadline_s - config.get("verification_reserve_s", DEFAULT_VERIFICATION_RESERVE_S)
    needed_s = recording_s + sync_s + processing_s
    available_s = end_s - now_s
    fits = needed_s <= available_s
    return dict(fits=fits, reason=None if fits else "RETRY_ROUND_DOES_NOT_FIT_DEADLINE", available_s=available_s, needed_s=needed_s,
                recording_deadline_s=end_s - processing_s - sync_s,
                components=dict(recording_s=recording_s, sync_s=sync_s, processing_s=processing_s, waves=waves, wave_s=wave_s,
                                task_s=task_s, processor_start_s=start_s, scene_count=scene_count, worker_count=worker_count,
                                processor_count=processor_count))


def default_processor_count(available_bytes):
    """min(12, floor(MemAvailable / 3 GiB)), at least 1."""
    return max(1, min(MAX_DEFAULT_PROCESSORS, int(available_bytes // PROCESSOR_MEMORY_BYTES)))


def processor_count_for(config, *, queue_length, available_bytes):
    """The configured `processor_count`, else the memory default; a processor with no scene to take is not launched."""
    wanted = config.get("processor_count")
    count = wanted if wanted is not None else default_processor_count(available_bytes)
    return max(1, min(count, queue_length))


def processing_max_attempts(config):
    return config.get("processing_max_attempts", DEFAULT_MAX_ATTEMPTS)


def read_mem_available_bytes(path="/proc/meminfo"):
    """MemAvailable of the Host in bytes."""
    with open(path, encoding="ascii") as stream:
        for line in stream:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    raise ValueError("MEM_AVAILABLE_UNKNOWN")
