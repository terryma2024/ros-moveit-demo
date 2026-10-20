"""A bounded pool of independent Host readbacks, one worker process per scene.

`verify_container_task_registration` is a pure function of the sealed files: it reads them, computes, and returns a proof or
raises. A wave's scenes are independent of one another, so their readbacks may run at the same time. This module only
*computes*: the parent process keeps every write, every comparison and the order of the verdict.

Design (see the tests in `test_readback_pool.py`):

* One short-lived interpreter per scene (`subprocess`, not `fork` and not `multiprocessing`): the Host owner is a multi-threaded
  asyncio process, which must not be forked, and a `spawn`ed `multiprocessing` child re-imports the main module and resolves
  `so101_demo` from whatever the environment finds. A child started with `python -c <bootstrap>` has no main module to
  re-import and takes its import resolution from the parent explicitly.
* Import guarantee: the parent sends its `sys.path` and, for `so101_demo` and `so101_teleop`, the module file and search path it
  has loaded (the Host CLI registers the worktree source through `so101_worktree_import`, which `sys.path` alone does not
  reproduce). The child registers the packages from exactly those locations, then refuses unless the readback code it is about
  to run is a file below them; the parent refuses unless the child reports the same locations back.
* Failure is refusal: a non-zero exit, a signal, a timeout, a missing or malformed result file, a result that is not exactly
  JSON-representable, or a different code tree each make the scene's readback raise `ValueError`; none is ever a pass or dropped.
* Results are returned in job order, whatever the completion order; the first failure in job order is the one raised, and no job
  after a known failure is started.
"""

import concurrent.futures
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

#: measured peak resident size of one scene readback on a real sealed episode (about 1.8 GB), rounded up
PEAK_BYTES_PER_READBACK = 2 * 1024**3
#: at most this share of the memory the kernel reports available may be committed to concurrent readbacks
MEMORY_SHARE = 0.6
DEFAULT_WORKER_CAP = 4
#: at the end of a campaign (shards and processors stopped, memory free) the default pool may be this large
FINALIZE_WORKER_CAP = 16
#: a readback that has not answered after this long is a refusal (a real one takes about half a minute)
DEFAULT_TIMEOUT_S = 1200.0
_PACKAGES = ('so101_demo', 'so101_teleop')
_REFUSAL = 'CONTAINER_TASK_READBACK_INVALID'
_TREE_MISMATCH = 'READBACK_WORKER_CODE_TREE_MISMATCH'

_BOOTSTRAP = r'''
import importlib.util, json, sys
request = json.loads(sys.stdin.read())
sys.path[:] = request["sys_path"]
for name, where in request["identity"].items():
    spec = importlib.util.spec_from_file_location(name, where["file"], submodule_search_locations=where["search"])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
from so101_demo.runtime.container_campaign.readback_pool import worker_main
sys.exit(worker_main(request))
'''


def default_readback_workers(*, available_bytes=None, cpu_count=None, finalize=False):
    """The pool size when the caller names none: bounded by the memory the kernel reports available and by the CPUs.

    ``finalize`` is the end-of-campaign readback (nothing else is running): the cap is `FINALIZE_WORKER_CAP` instead of 4."""
    if available_bytes is None:
        try:
            for line in Path('/proc/meminfo').read_text().splitlines():
                if line.startswith('MemAvailable:'):
                    available_bytes = int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return 1
    if type(available_bytes) is not int:
        return 1
    cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 1)
    by_memory = math.floor(available_bytes * MEMORY_SHARE / PEAK_BYTES_PER_READBACK)
    return max(1, min(FINALIZE_WORKER_CAP if finalize else DEFAULT_WORKER_CAP, by_memory, max(1, cpus // 2)))


def resolve_readback_workers(value, *, finalize=False):
    """`None` selects the default (the end-of-campaign default with ``finalize``); otherwise a positive int, where 1 is the in-process
    serial path."""
    if value is None:
        return default_readback_workers(finalize=finalize)
    if type(value) is not int or value < 1:
        raise ValueError('READBACK_WORKERS_INVALID')
    return value


def import_identity():
    """Where this process loaded the SO-101 packages from: the module file and search path of each."""
    identity = {}
    for name in _PACKAGES:
        module = sys.modules.get(name)
        if module is not None and getattr(module, '__file__', None) and getattr(module, '__path__', None):
            identity[name] = dict(file=str(module.__file__), search=[str(item) for item in module.__path__])
    if 'so101_demo' not in identity:
        raise ValueError(_TREE_MISMATCH)
    return identity


def assert_same_code_tree(identity):
    """Refuse unless this process runs the code `identity` names: the packages and the readback code are files below it."""
    if set(identity) - set(_PACKAGES) or 'so101_demo' not in identity:
        raise ValueError(_TREE_MISMATCH)
    if import_identity_of(identity) != identity:
        raise ValueError(_TREE_MISMATCH)
    from so101_demo.act import result_store

    roots = tuple(os.path.realpath(item) + os.sep for item in identity['so101_demo']['search'])
    for module in (result_store, sys.modules[__name__]):
        if not os.path.realpath(module.__file__).startswith(roots):
            raise ValueError(_TREE_MISMATCH)


def import_identity_of(identity):
    """The identity this process has for the packages `identity` names."""
    found = {}
    for name in identity:
        module = sys.modules.get(name)
        if module is None or not getattr(module, '__file__', None) or not getattr(module, '__path__', None):
            raise ValueError(_TREE_MISMATCH)
        found[name] = dict(file=str(module.__file__), search=[str(item) for item in module.__path__])
    return found


def worker_main(request):
    """The child: read one scene back and write the answer to the result file. Returns the process exit code."""
    result_path = Path(request['result_path'])
    try:
        assert_same_code_tree(request['identity'])
        from so101_demo.act.result_store import verify_container_task_registration

        job = request['job']
        try:
            if 'processing' in job:
                # a phase-2 job: the processed result of one scene, read back against its phase-1 record
                from so101_demo.act.processed_result import verify_processed_result

                arguments = dict(job['processing'])
                proof = verify_processed_result(arguments.pop('output_dir'), sealed=Path(arguments.pop('sealed')),
                    scope=Path(job['scope']), inputs_manifest=Path(job['inputs_manifest']), **arguments)
            else:
                proof = verify_container_task_registration(Path(job['registration']), scope=Path(job['scope']),
                                                           inputs_manifest=Path(job['inputs_manifest']))
            body = dict(ok=True, proof=proof)
            if json.loads(json.dumps(proof, allow_nan=False)) != proof:
                raise ValueError('proof is not JSON-exact')
        except ValueError as error:
            body = dict(ok=False, refusal=str(error) or _REFUSAL)
        body['identity'] = import_identity_of(request['identity'])
        temporary = result_path.with_name(result_path.name + '.partial')
        temporary.write_text(json.dumps(body, allow_nan=False))
        os.replace(temporary, result_path)
        return 0
    except BaseException as error:  # the parent reads a missing result file as a refusal; the reason goes to stderr
        print(f'readback worker failed: {type(error).__name__}: {error}', file=sys.stderr)
        return 3


def _run_one(index, job, *, floor, lock, **context):
    """(index, answer) for one scene; `answer` is the proof, or an Exception that refuses the scene. Never raises.

    A refusal lowers `floor` here, in the worker thread, before the next queued scene looks at it."""
    with lock:
        skipped = floor[0] is not None and index > floor[0]
    answer = ValueError('CONTAINER_READBACK_WORKER_SKIPPED:' + job['scene_id']) if skipped else _attempt(index, job, **context)
    if isinstance(answer, Exception) and not skipped:
        with lock:
            floor[0] = index if floor[0] is None else min(floor[0], index)
    return index, answer


def _attempt(index, job, *, directory, identity, request_identity, timeout_s, executable):
    scene = job['scene_id']
    result_path = directory / f'result-{index}.json'
    request = dict(sys_path=list(sys.path), identity=request_identity, result_path=str(result_path),
                   job={key: job[key] for key in ('registration', 'scope', 'inputs_manifest', 'processing') if key in job})
    try:
        completed = subprocess.run([executable, '-c', _BOOTSTRAP], input=json.dumps(request), text=True,
                                   capture_output=True, timeout=timeout_s, env=dict(os.environ), check=False)
    except subprocess.TimeoutExpired:
        return ValueError('CONTAINER_READBACK_WORKER_TIMEOUT:' + scene)
    except (OSError, ValueError) as error:
        return ValueError('CONTAINER_READBACK_WORKER_LAUNCH_FAILED:' + scene + ':' + type(error).__name__)
    if completed.returncode != 0:
        return ValueError(f'CONTAINER_READBACK_WORKER_EXITED:{scene}:{completed.returncode}')
    try:
        body = json.loads(result_path.read_text())
        if type(body) is not dict or body.get('identity') != identity:
            return ValueError(_TREE_MISMATCH + ':' + scene)
        if body.get('ok') is True and type(body.get('proof')) is dict and set(body) == {'ok', 'proof', 'identity'}:
            return body['proof']
        if body.get('ok') is False and type(body.get('refusal')) is str and set(body) == {'ok', 'refusal', 'identity'}:
            return ValueError(body['refusal'])
    except (OSError, ValueError, UnicodeError):
        pass
    return ValueError('CONTAINER_READBACK_WORKER_UNREADABLE:' + scene)


def run_readbacks(jobs, *, workers, timeout_s=DEFAULT_TIMEOUT_S, _request_identity=None, _executable=None):
    """Read every job back, at most `workers` at a time; the answers in job order.

    Each job is `dict(scene_id, registration, scope, inputs_manifest)`. The answer is the readback proof, or the `ValueError` the
    serial path would have raised for that scene (a worker failure is a `ValueError` too). Answers after the first refusal in job
    order may be `CONTAINER_READBACK_WORKER_SKIPPED` refusals: the caller raises the first one anyway. `_request_identity` and
    `_executable` are test seams."""
    workers = resolve_readback_workers(workers)
    timeout_s = DEFAULT_TIMEOUT_S if timeout_s is None else timeout_s
    if type(timeout_s) not in (int, float) or not timeout_s > 0:
        raise ValueError('READBACK_TIMEOUT_INVALID')
    identity = import_identity()
    floor = [None]
    lock = threading.Lock()
    answers = [None] * len(jobs)
    with tempfile.TemporaryDirectory(prefix='so101-readback-') as name:
        directory = Path(name)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(workers, len(jobs)))) as executor:
            pending = [executor.submit(_run_one, index, job, directory=directory, identity=identity,
                                       request_identity=_request_identity or identity, timeout_s=timeout_s, floor=floor,
                                       lock=lock, executable=_executable or sys.executable)
                       for index, job in enumerate(jobs)]
            for future in concurrent.futures.as_completed(pending):
                index, answer = future.result()
                answers[index] = answer
    return answers
