"""Bounded `docker inspect` for stop and cleanup proofs.

A slow Docker daemon (right after many containers stop at once and gigabytes of bags were written) can time one inspect
out. A timed-out inspect says nothing about the container, so it is "not yet known": retry with backoff until a total bound.
A definite answer (any finished docker process, including `No such object`) ends the wait at once and is judged by the
caller exactly as before. Only after the bound does the wait itself fail, with every attempt summarised."""
import subprocess
import time

INSPECT_CALL_TIMEOUT_S = 30        # the per-call timeout of the docker runner (service_owner._docker)
INSPECT_BOUND_S = 180              # total wait for an answer before the inspect counts as unconfirmed
INSPECT_BACKOFF_FIRST_S = 2.0
INSPECT_BACKOFF_MAX_S = 20.0
TRANSIENT_DAEMON_MARKERS = ('error during connect', 'cannot connect to the docker daemon')

_clock = time.monotonic
_sleep = time.sleep


def _transient_reason(result):
    if result.returncode == 0:
        return None
    text = str(result.stderr or '').lower()
    if 'no such object' in text or 'no such container' in text:
        return None
    if any(marker in text for marker in TRANSIENT_DAEMON_MARKERS):
        return 'DAEMON_ERROR: ' + str(result.stderr).strip()[:200]
    return None


def bounded_docker_inspect(docker_runner, argv, *, bound_s=None):
    """Run `argv` (a docker inspect) until a definite answer; return that finished process result.

    Raises ValueError('DOCKER_INSPECT_UNCONFIRMED attempts=N first=... last=...') when only transient failures were seen
    within `bound_s` (default INSPECT_BOUND_S)."""
    bound = INSPECT_BOUND_S if bound_s is None else bound_s
    start = _clock()
    reasons, delay = [], INSPECT_BACKOFF_FIRST_S
    while True:
        try:
            result = docker_runner(argv)
        except subprocess.TimeoutExpired as error:
            reasons.append('TimeoutExpired: ' + str(error))
        else:
            transient = _transient_reason(result)
            if transient is None:
                return result
            reasons.append(transient)
        if _clock() - start + delay >= bound:
            raise ValueError('DOCKER_INSPECT_UNCONFIRMED attempts=%d first=%s last=%s' % (
                len(reasons), reasons[0], reasons[-1]))
        _sleep(delay)
        delay = min(delay * 2, INSPECT_BACKOFF_MAX_S)
