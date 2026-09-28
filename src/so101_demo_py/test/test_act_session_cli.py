"""Task 14 CLI: the composition is built first, and only then is a spec submitted."""

import json
from pathlib import Path

import pytest

from so101_demo.cli.act_session import main

PACKAGE = Path(__file__).resolve().parents[1]


class _Service:
    def __init__(self):
        self.specs = []

    def start(self, spec):
        self.specs.append(spec)
        return {"status": "PASSED"}


def _ports():
    from types import SimpleNamespace

    class _Port:
        def request(self, name, payload):
            return {"ok": True}

    class _Inference:
        def submit(self, observation, *, sequence):
            return sequence

    return SimpleNamespace(commander_id="operator-1"), _Port(), _Inference()


def test_a_planning_run_submits_only_its_spec_and_needs_no_bundle(tmp_path, capsys):
    service = _Service()
    assert main(["--mode", "dry_run", "--evidence-root", str(tmp_path)],
                service_factory=lambda _spec: service, ports_factory=_ports) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["mode"] == "dry_run" and printed["effects"] is False
    spec = service.specs[0]
    assert spec["kind"] == "act_session" and spec["payload"]["effects"] is False
    assert spec["payload"]["artifacts"] == {}
    assert "observation" not in json.dumps(spec)          # no frame, no model input, in a plan


def test_an_execute_run_refuses_before_any_service_exists(tmp_path):
    built = []
    argv = ["--mode", "execute", "--evidence-root", str(tmp_path)]
    with pytest.raises(ValueError, match="ACT_EXECUTE_BUNDLE_REQUIRED"):
        main(argv, service_factory=lambda spec: built.append(spec) or _Service(), ports_factory=_ports)
    assert built == []                                    # nothing was submitted
    missing = ["--bundle", str(tmp_path / "absent.json"), "--calibration", str(tmp_path / "c.json"),
               "--policy", str(tmp_path / "p.json"), "--activation-receipt", str(tmp_path / "r.json"),
               "--runtime-config", str(tmp_path / "rt.yaml")]
    with pytest.raises(ValueError, match="ACT_EXECUTE_BUNDLE_REQUIRED"):
        main(["--mode", "execute", "--evidence-root", str(tmp_path), *missing],
             service_factory=lambda spec: built.append(spec) or _Service(), ports_factory=_ports)
    assert built == []


def test_the_production_factories_fail_closed(tmp_path, monkeypatch):
    """Composing the real service demands the registered evidence root before anything else.

    That refusal arrives as SystemExit from the service's own bootstrap, which is how every live CLI in this
    repo behaves; the assertion here records that the production path refuses rather than proceeding on a
    guessed root.
    """

    from so101_demo.cli.act_session import _composition_ports

    monkeypatch.delenv("SO101_UNIFIED_EVIDENCE_ROOT", raising=False)
    with pytest.raises((SystemExit, ValueError)) as error:
        _composition_ports()
    assert "EVIDENCE_ROOT" in str(error.value)
