"""Bounded `docker inspect` of stop proofs: a timed-out or daemon-error inspect is "not yet known", a definite answer is final.

Controlled doubles: the docker runner, the clock and the sleep. Nothing here talks to a Docker daemon."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from so101_demo.runtime.container_campaign import docker_inspect
from so101_demo.runtime.container_campaign.service_owner import ContainerServiceOwner
from so101_demo.runtime.container_campaign.shard_owner import ContainerShardOwner

DOCUMENT = dict(Id='a' * 64, State=dict(Running=False, ExitCode=0))
OK = SimpleNamespace(returncode=0, stdout=json.dumps([DOCUMENT]), stderr='')
TIMEOUT = subprocess.TimeoutExpired(['docker', 'inspect'], 30)


class Script:
    def __init__(self):
        self.outcomes, self.calls, self.sleeps, self.now = [], 0, [], 0.0

    def runner(self, argv):
        self.calls += 1
        self.now += 30    # every attempt costs the per-call timeout, the worst case
        outcome = self.outcomes.pop(0) if self.outcomes else TIMEOUT
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def script(monkeypatch):
    holder = Script()
    monkeypatch.setattr(docker_inspect, '_clock', lambda: holder.now)
    monkeypatch.setattr(docker_inspect, '_sleep', holder.sleep)
    return holder


def test_timeouts_then_success_is_proven_after_backoff(script):
    script.outcomes = [TIMEOUT, TIMEOUT, OK]
    result = docker_inspect.bounded_docker_inspect(script.runner, ['docker', 'inspect', 'x'])
    assert result is OK and script.calls == 3 and len(script.sleeps) == 2
    assert script.sleeps[1] > script.sleeps[0]


def test_daemon_connect_error_is_retried(script):
    down = SimpleNamespace(returncode=1, stdout='', stderr='error during connect: Get http://docker.sock: EOF')
    script.outcomes = [down, SimpleNamespace(returncode=1, stdout='', stderr='Cannot connect to the Docker daemon at x'), OK]
    assert docker_inspect.bounded_docker_inspect(script.runner, ['docker', 'inspect', 'x']) is OK
    assert script.calls == 3


def test_timeouts_past_the_bound_are_unconfirmed_with_attempts_recorded(script):
    with pytest.raises(ValueError) as caught:
        docker_inspect.bounded_docker_inspect(script.runner, ['docker', 'inspect', 'x'])
    message = str(caught.value)
    assert message.startswith('DOCKER_INSPECT_UNCONFIRMED attempts=') and 'TimeoutExpired' in message
    assert script.calls >= 3 and f'attempts={script.calls}' in message
    assert script.now <= docker_inspect.INSPECT_BOUND_S + docker_inspect.INSPECT_CALL_TIMEOUT_S


def test_definite_answers_end_the_wait_at_once(script):
    missing = SimpleNamespace(returncode=1, stdout='', stderr='Error: No such object: x')
    for answer in (OK, missing):
        script.outcomes, script.calls, script.sleeps = [answer], 0, []
        assert docker_inspect.bounded_docker_inspect(script.runner, ['docker', 'inspect', 'x']) is answer
        assert script.calls == 1 and script.sleeps == []


def test_shard_owner_inspect_survives_transient_timeouts(script):
    script.outcomes = [TIMEOUT, TIMEOUT, OK]
    owner = SimpleNamespace(docker=script.runner)
    assert ContainerShardOwner.inspect(owner, 'a' * 64) == DOCUMENT


def test_shard_owner_inspect_fails_closed_past_the_bound(script):
    with pytest.raises(ValueError, match='DOCKER_INSPECT_UNCONFIRMED'):
        ContainerShardOwner.inspect(SimpleNamespace(docker=script.runner), 'a' * 64)


def test_service_owner_inspect_container_survives_transient_timeouts(script):
    script.outcomes = [TIMEOUT, OK]
    owner = SimpleNamespace(docker_runner=script.runner)
    assert ContainerServiceOwner.inspect_container(owner, 'a' * 64) == DOCUMENT
