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
