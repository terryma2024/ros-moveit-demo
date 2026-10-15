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

DEFAULT_RESERVE_S = 1800
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_VERIFICATION_RESERVE_S = 600
#: one processing task: the offline processor (`act.offline.orchestration.PROCESSING_TIMEOUT_S`, 1200 s) plus its seal margin and the
#: task-result publication; the config key `processing_task_timeout_s` may not be lower (`runtime.inference.config`)
DEFAULT_TASK_TIMEOUT_S = 1800
MAX_DEFAULT_PROCESSORS = 12
#: the processor peaks at 2.2 GiB and its QC child runs after it
PROCESSOR_MEMORY_BYTES = 3 * 2**30


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
