"""Stall accounting (T0b): who ran and who waited over a heartbeat stall, and the stack summaries."""

import threading
from types import SimpleNamespace

import pytest

from so101_demo.act.stall_diagnostics import StallMonitor, ThreadSampler, classify_stall

from test_act_stall_diagnostics import FakeClock, _pair


class FakeSampler:
    """A sampler whose per-thread (run_ns, wait_ns) the test advances between beats."""

    def __init__(self):
        self.counters = {1: [0, 0], 2: [0, 0], 3: [0, 0]}                 # tid 1 heartbeat, 2 a Python worker, 3 a native thread
        self.stack_calls = 0

    def cpu(self):
        return {tid: tuple(value) for tid, value in self.counters.items()}

    def names(self):
        return {1: ("act-stall-heartbeat", True), 2: ("act-rollout-inference", True), 3: ("fastdds-recv", False)}

    def stacks(self, skip_ident=None):
        self.stack_calls += 1
        return {"act-rollout-inference": ["lerobot.py:200 infer", "rollout_ros.py:260 _work", "threading.py:1 run"]}


def _monitor_with(sampler, clock, delays):
    return StallMonitor(monotonic=clock.monotonic, sampler=sampler, sample_period_s=0.010,
                        sleep=lambda s: setattr(clock, "now", clock.now + delays.pop(0)))


@pytest.fixture(autouse=True)
def _heartbeat_is_tid_1(monkeypatch):
    monkeypatch.setattr("so101_demo.act.stall_diagnostics.threading.get_native_id", lambda: 1)


def test_classify_stall_tells_a_gil_holder_from_not_scheduled_from_a_native_burner_from_nobody():
    names = {1: ("hb", True), 2: ("worker", True), 3: ("recv", False)}
    assert classify_stall(window_s=0.020, deltas={1: (0, 0.015), 2: (0, 0), 3: (0, 0)}, heartbeat_tid=1, names=names) == ("unscheduled", None)
    assert classify_stall(window_s=0.020, deltas={1: (0, 0), 2: (0.018, 0), 3: (0.001, 0)}, heartbeat_tid=1, names=names) == ("gil_holder", "worker")
    assert classify_stall(window_s=0.020, deltas={1: (0, 0), 2: (0.001, 0), 3: (0.019, 0)}, heartbeat_tid=1, names=names) == ("native_cpu", "recv")
    assert classify_stall(window_s=0.020, deltas={1: (0, 0), 2: (0.001, 0), 3: (0.001, 0)}, heartbeat_tid=1, names=names) == ("nobody_ran", None)


def test_a_stall_over_the_threshold_is_accounted_with_the_thread_that_burned_cpu():
    clock, sampler, delays = FakeClock(), FakeSampler(), [0.001, 0.001, 0.020]
    monitor = _monitor_with(sampler, clock, delays)
    now = monitor.beat(clock.now)                                    # baseline taken
    now = monitor.beat(now)
    sampler.counters[2][0] += 19_000_000                             # the worker ran 19 ms during the next gap
    stalled = monitor.beat(now)
    assert list(monitor.stalls)[-1] == (now, stalled)
    detail = monitor.details[now]
    assert detail["classification"] == "gil_holder" and detail["holder"] == "act-rollout-inference"
    assert detail["process_cpu_s"] == pytest.approx(0.019) and detail["threads"][0]["name"] == "act-rollout-inference"
    assert detail["stacks_at_wakeup"]["act-rollout-inference"][0] == "lerobot.py:200 infer"


def test_a_stall_where_the_heartbeat_was_runnable_but_not_running_is_unscheduled():
    clock, sampler, delays = FakeClock(), FakeSampler(), [0.001, 0.025]
    monitor = _monitor_with(sampler, clock, delays)
    now = monitor.beat(clock.now)
    sampler.counters[1][1] += 24_000_000                             # the heartbeat waited for a CPU
    monitor.beat(now)
    assert monitor.details[now]["classification"] == "unscheduled"


def test_stack_summaries_are_stored_at_most_once_a_second():
    clock, sampler, delays = FakeClock(), FakeSampler(), [0.001, 0.020, 0.020, 0.020]
    monitor = _monitor_with(sampler, clock, delays)
    now = monitor.beat(clock.now)
    starts = []
    for _ in range(3):
        starts.append(now)
        now = monitor.beat(now)
    stored = [start for start in starts if "stacks_at_wakeup" in monitor.details[start]]
    assert stored == [starts[0]] and sampler.stack_calls == 1


def test_a_stall_under_the_cpu_threshold_is_listed_but_has_no_account():
    clock, sampler, delays = FakeClock(), FakeSampler(), [0.001, 0.006]
    monitor = _monitor_with(sampler, clock, delays)
    now = monitor.beat(clock.now)
    monitor.beat(now)
    assert len(monitor.stalls) == 1 and not monitor.details


def test_the_summary_counts_the_classifications_and_a_failed_pair_carries_the_account():
    clock, sampler, delays = FakeClock(), FakeSampler(), [0.001, 0.020]
    monitor = _monitor_with(sampler, clock, delays)
    now = monitor.beat(clock.now)
    sampler.counters[2][0] += 18_000_000
    end = monitor.beat(now)
    pair = _pair(5, send=now + 0.002, check=end, sent_done=now + 0.002)
    summary = monitor.summary(since_s=0.0, until_s=end + 1, pairs=[pair])
    assert summary["heartbeat"]["classified"]["classification"] == {"gil_holder": 1}
    assert summary["heartbeat"]["classified"]["gil_holders"] == {"act-rollout-inference": 1}
    assert summary["pairs"][0]["heartbeat_stalls"][0]["account"]["classification"] == "gil_holder"


def test_the_time_the_monitor_spends_accounting_is_not_a_stall_of_the_process():
    clock = FakeClock()

    class Slow(FakeSampler):
        def cpu(self):
            clock.now += 0.009                                       # reading /proc takes 9 ms of the heartbeat thread
            return super().cpu()

    delays = [0.001, 0.001, 0.001]
    monitor = _monitor_with(Slow(), clock, delays)
    now = clock.now
    for _ in range(3):
        now = monitor.beat(now)
    assert not monitor.stalls and monitor.account_s == pytest.approx(0.027)
    assert monitor.summary(since_s=0.0, until_s=now + 1)["heartbeat"]["accounting_s_total"] == pytest.approx(0.027)


def test_a_failing_sampler_never_stops_the_heartbeat():
    class Broken(FakeSampler):
        def cpu(self):
            raise OSError("proc gone")

    clock, delays = FakeClock(), [0.001, 0.020]
    monitor = _monitor_with(Broken(), clock, delays)
    now = monitor.beat(clock.now)
    monitor.beat(now)
    assert len(monitor.stalls) == 1 and monitor.wakeups == 2


def test_the_sampler_reads_schedstat_comm_and_python_thread_names(tmp_path):
    for tid, (run, wait, comm) in {101: (5_000_000, 1_000, "fastdds"), 102: (7, 8, "python3")}.items():
        task = tmp_path / str(tid)
        task.mkdir()
        (task / "schedstat").write_text(f"{run} {wait} 3\n")
        (task / "comm").write_text(comm + "\n")
    (tmp_path / "103").mkdir()                                       # a thread without schedstat (ended): skipped
    sampler = ThreadSampler(proc_root=str(tmp_path), threads=lambda: [SimpleNamespace(native_id=102, name="act-rollout-spin", ident=9)],
                            current_frames=lambda: {})
    assert sampler.cpu() == {101: (5_000_000, 1_000), 102: (7, 8)}
    assert sampler.names()[101] == ("fastdds", False) and sampler.names()[102] == ("act-rollout-spin", True)


def test_the_real_sampler_sees_this_process_and_its_stacks():
    sampler = ThreadSampler()
    assert threading.current_thread().native_id in sampler.cpu()
    stacks = sampler.stacks()
    assert stacks and all(len(rows) <= 3 for rows in stacks.values())
