import json
from types import SimpleNamespace

from so101_demo.act.offline import raw_recorder


def test_pilot_starts_and_stops_only_owned_data_process_after_teacher(tmp_path):
    from so101_demo.act.offline import pilot

    actions = []

    class Processes:
        def start(self, spec, *, environment):
            actions.append(("start", spec.argv, environment))
            ready = tmp_path / "raw" / "ready.json"
            ready.write_text(json.dumps({"schema": raw_recorder.READY_SCHEMA, "state": "RECORDING"}))
            return "owned"

        def exit_code(self, identity):
            return None

        def terminate(self, identity, grace_s):
            actions.append(("terminate", identity, grace_s))
            (tmp_path / "raw" / "record-stats.json").write_text(json.dumps({"closed": True}))
            return 0

        def stop(self, identity):
            actions.append(("stop", identity))

    sidecar = pilot.PilotRecording(processes=Processes(), root=tmp_path / "raw", environment={},
                                   spec_factory=lambda argv: SimpleNamespace(argv=argv), timeout_s=1.0)
    sidecar.start()
    assert sidecar.ready and len(actions) == 1
    assert sidecar.finish()["closed"]
    assert [action[0] for action in actions] == ["start", "terminate", "stop"]


def test_pilot_start_failure_is_data_evidence_and_never_raises(tmp_path):
    from so101_demo.act.offline import pilot

    def failed(*args, **kwargs):
        raise OSError("disk unavailable")

    sidecar = pilot.PilotRecording(processes=SimpleNamespace(start=failed), root=tmp_path / "raw", environment={},
                                   spec_factory=lambda argv: SimpleNamespace(argv=argv), timeout_s=1.0)
    sidecar.start()
    assert not sidecar.ready
    assert sidecar.finish()["failure"].startswith("RAW_PILOT_START_FAILED")
