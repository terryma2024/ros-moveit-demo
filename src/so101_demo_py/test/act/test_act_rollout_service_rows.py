"""The policy service's account of a reply is recorded in the step rows, and only when there is one."""

from test_act_rollout_episode import Inference, Ports, Sink, _run

SERVICE = {"outcome": "OK", "queue_wait_ms": 1.25, "inference_ms": 8.5, "inflight_at_receipt": 2, "bundle_sha256": "a" * 64}


class ServiceInference(Inference):
    def __init__(self, clock, script=(), polls_before_reply=2):
        super().__init__(clock, script, polls_before_reply)
        self.last_service = None

    def poll(self):
        try:
            reply = super().poll()
        except ValueError:
            self.last_service = dict(SERVICE, outcome="QUEUE_TIMEOUT")
            raise
        if reply:
            reply = dict(reply, service=dict(SERVICE))
            self.last_service = reply["service"]
        return reply


def test_an_applied_step_and_a_late_step_carry_the_services_account():
    ports = Ports(script=("ok", "stale", "ok", "ok"))
    ports.inference = ServiceInference(ports.clock, ("ok", "stale", "ok", "ok"))
    sink = Sink()
    _run(ports, sink)
    applied = [row for row in sink.steps if row.get("applied")]
    late = [row for row in sink.steps if row.get("late")]
    assert applied and all(row["service"] == SERVICE for row in applied)
    assert late and all(row["service"]["outcome"] == "QUEUE_TIMEOUT" for row in late)


def test_without_an_account_the_rows_are_unchanged():
    sink = Sink()
    _run(Ports(), sink)
    assert sink.steps and all("service" not in row for row in sink.steps)


def test_the_episode_result_counts_the_services_replies_by_outcome_and_gives_the_three_times():
    ports = Ports(script=("ok", "stale", "ok", "ok"))
    ports.inference = ServiceInference(ports.clock, ("ok", "stale", "ok", "ok"))
    sink = Sink()
    result = _run(ports, sink)
    summary = result["service"]
    rows = [row for row in sink.steps if row.get("service")]
    assert summary["replies"] == len(rows) and summary["replies"] > 0
    assert summary["outcomes"] == {"OK": sum(1 for row in rows if row["service"]["outcome"] == "OK"),
                                   "QUEUE_TIMEOUT": sum(1 for row in rows if row["service"]["outcome"] == "QUEUE_TIMEOUT")}
    assert summary["queue_wait_ms"]["p50"] == 1.25 and summary["inference_ms"]["max"] == 8.5
    assert summary["round_trip_s"]["n"] == len(rows) and summary["round_trip_s"]["max"] >= summary["round_trip_s"]["p50"]


def test_an_in_process_model_leaves_no_service_summary_in_the_result():
    assert "service" not in _run(Ports(), Sink())
