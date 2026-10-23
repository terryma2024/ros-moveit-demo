"""Campaign selection, station residue and the campaign verdict."""

from __future__ import annotations

import os
from pathlib import Path
import time

from so101_demo.cli.macos_campaign.guard import CampaignRouteSpec, RefusedRun
from so101_demo.cli.macos_campaign.journal import (
    MPS_TWO_WORKER_FIRST_PASS,
    TWO_WORKER_FIRST_PASS_BATCH_KIND,
)
from so101_demo.parallel_batch import point_drain
from so101_demo.parallel_batch.contracts.macos_two_worker import (
    ParallelRuntimeConfigMacosMpsTwoWorker,
)
from so101_demo.parallel_batch.queue import DurablePointQueue
from so101_demo.parallel_batch.single_worker_composition import (
    SINGLE_WORKER_RETRY_BATCH_KIND,
)
from so101_demo.parallel_batch.two_worker_composition import (
    compose_two_worker_campaign,
)


def campaign_status(*, cleanup_complete: bool, results, workers, served, refused,
                    points) -> str:
    """The exact two-worker verdict: the same rule `campaign_verdict` applies to every route.

    It requires the whole happy path *and* the executed point set: cleanup complete, one result
    document per Worker spawn, every spawn `ACTIVE`, at least six served requests whose devices are
    exactly `["mps"]`, no refused request at all, and `points["complete"]` - every selected point
    executed exactly once, with its evidence, and no unselected point attempted. A verdict that
    asserted nothing about the point set is what let empty campaigns report PASS.
    """

    spec = CampaignRouteSpec(
        execution_profile=MPS_TWO_WORKER_FIRST_PASS, batch_kind=TWO_WORKER_FIRST_PASS_BATCH_KIND,
        config_class=ParallelRuntimeConfigMacosMpsTwoWorker, module="so101_demo.cli.macos_two_worker_campaign",
        worker_ids=("worker-01", "worker-02"), default_point_ids=("p1", "p2"), minimum_served=6,
        composer=compose_two_worker_campaign)
    return campaign_verdict(spec=spec, cleanup_complete=cleanup_complete, results=results,
                            workers=workers, served=served, refused=refused, points=points)


def installed_catalog_path() -> Path:
    """The installed point catalog, which is what a service-resolved selection uses."""

    try:
        from ament_index_python.packages import get_package_share_directory

        return Path(get_package_share_directory("so101_demo_py")) \
            / point_drain.INSTALLED_CATALOG_RELATIVE
    except Exception as error:  # noqa: BLE001 - a missing catalog is a refusal, not a traceback
        raise RefusedRun("config", f"CATALOG_MISSING: {type(error).__name__}: {error}") from error


def selection_document(selection, *, catalog_path: Path, extras=None) -> dict:
    """The audit projection of the one selection this campaign executes.

    It is produced by the same function that writes `selection-binding.json`, so a first pass and a
    retry project the identical shape - including the retry's original selection/result chain and
    how it was verified - instead of the retry path crashing on a first-pass-only field.
    """

    return point_drain.selection_document_for(selection, catalog_path=catalog_path, extras=extras)


def bind_campaign_selection(*, arguments, plan, spec):
    """Freeze the selection binding and open the durable queue it drains.

    A first pass takes the ordered `--point-id` list (the four anchors are required by the binding
    contract, so a selection that omits them is refused by name rather than silently extended). A
    v5 retry takes exactly one point and must reference the prior campaign's committed business
    `FAILED` result; anything else - an unrun point, an infrastructure failure, an indeterminate
    point - is refused before a process exists. Returns the binding, its durable queue and the
    catalog path the binding was frozen from, which is what the selection document records.
    """

    from so101_demo.parallel_batch.selection import SelectionError, load_point_catalog

    retry = spec.batch_kind == SINGLE_WORKER_RETRY_BATCH_KIND
    point_ids = tuple(arguments.point_id)
    catalog_argument = getattr(arguments, "catalog", None)
    expected_catalog_sha256 = getattr(arguments, "catalog_sha256", None)
    try:
        if retry:
            # A retry binding is named one of two ways, and both must name an *original result*:
            # the prior campaign root (`--retry-root`, whose committed result document is re-read
            # and hashed) or the service's already-admitted chain (`--original-selection-sha256`
            # with `--original-result-sha256`, optionally with the original result document so its
            # bytes decide). There is no form that starts a retry without a named original result.
            retry_root = getattr(arguments, "retry_root", None)
            selection_sha = getattr(arguments, "original_selection_sha256", None)
            result_sha = getattr(arguments, "original_result_sha256", None)
            catalog_sha = getattr(arguments, "original_catalog_sha256", None)
            original_result = getattr(arguments, "original_result", None)
            original_batch_id = getattr(arguments, "original_batch_id", None)
            if len(point_ids) != 1:
                raise RefusedRun("selection", "RETRY_POINT_REQUIRED", exit_code=2)
            if retry_root is None and selection_sha is None and result_sha is None:
                raise RefusedRun(
                    "selection",
                    "RETRY_ROOT_REQUIRED: name the original chain with --retry-root or with "
                    "--original-selection-sha256 and --original-result-sha256",
                    exit_code=2)
            if retry_root is None and (selection_sha is None or result_sha is None):
                raise RefusedRun(
                    "selection",
                    "RETRY_ROOT_REQUIRED: --original-selection-sha256 and "
                    "--original-result-sha256 are both required without --retry-root",
                    exit_code=2)
            if original_batch_id is not None and original_batch_id == arguments.batch_id:
                raise RefusedRun("selection", "RETRY_BATCH_EXISTS", exit_code=2)
            extras = {"original_batch_id": original_batch_id}
            if retry_root is not None:
                source = point_drain.read_retry_source(prior_root=Path(retry_root),
                                                       point_id=point_ids[0])
                prior = point_drain.read_selection_document(
                    Path(retry_root) / point_drain.SELECTION_DOCUMENT_BASENAME)
                if str(prior["campaign_id"]) != arguments.campaign_id:
                    raise RefusedRun(
                        "selection",
                        f"RETRY_CAMPAIGN_MISMATCH: {prior['campaign_id']} != "
                        f"{arguments.campaign_id}", exit_code=2)
                if str(prior["batch_id"]) == arguments.batch_id:
                    raise RefusedRun("selection", "RETRY_BATCH_EXISTS", exit_code=2)
                # A digest named beside the root may only *confirm* what the root's own bytes say.
                for name, declared, recorded in (
                        ("original_selection_sha256", selection_sha,
                         str(prior["selection_sha256"])),
                        ("original_result_sha256", result_sha,
                         str(source["original_result_sha256"])),
                        ("original_catalog_sha256", catalog_sha,
                         str(prior["catalog_sha256"]))):
                    if declared is not None and declared != recorded:
                        raise RefusedRun(
                            "selection",
                            f"RETRY_SOURCE_MISMATCH: {name} {declared} != {recorded}",
                            exit_code=2)
                extras["original_batch_id"] = original_batch_id or str(prior["batch_id"])
                catalog_path = (Path(catalog_argument) if catalog_argument is not None
                                else Path(str(source["catalog_path"])))
                if (catalog_argument is not None and catalog_path.resolve()
                        != Path(str(source["catalog_path"])).resolve()):
                    raise RefusedRun("selection", "RETRY_CATALOG_MISMATCH", exit_code=2)
            else:
                catalog_path = (Path(catalog_argument) if catalog_argument is not None
                                else installed_catalog_path())
                source = point_drain.retry_source_from_hashes(
                    point_id=point_ids[0], original_selection_sha256=selection_sha,
                    original_result_sha256=result_sha,
                    original_catalog_sha256=(
                        catalog_sha if catalog_sha is not None
                        else load_point_catalog(catalog_path).sha256),
                    original_result_path=original_result,
                    original_batch_id=original_batch_id)
            extras["original_result_source"] = source.get("original_result_source")
            catalog = load_point_catalog(catalog_path)
            closure = point_drain.runtime_closure_sha256(
                catalog_path=catalog_path, catalog_sha256=catalog.sha256,
                config_sha256=plan.config_sha256)
            selection = point_drain.retry_binding(
                source=source, catalog_path=catalog_path, campaign_id=arguments.campaign_id,
                batch_id=arguments.batch_id, config_sha256=plan.config_sha256,
                runtime_closure_sha256=closure,
                expected_catalog_sha256=expected_catalog_sha256)
        else:
            extras = {}
            if not point_ids:
                raise RefusedRun("selection", "SELECTED_POINTS_REQUIRED", exit_code=2)
            catalog_path = (Path(catalog_argument) if catalog_argument is not None
                            else installed_catalog_path())
            catalog = load_point_catalog(catalog_path)
            closure = point_drain.runtime_closure_sha256(
                catalog_path=catalog_path, catalog_sha256=catalog.sha256,
                config_sha256=plan.config_sha256)
            selection = point_drain.first_pass_binding(
                catalog_path=catalog_path, point_ids=point_ids,
                campaign_id=arguments.campaign_id, batch_id=arguments.batch_id,
                config_sha256=plan.config_sha256, runtime_closure_sha256=closure,
                expected_catalog_sha256=expected_catalog_sha256)
    except (SelectionError, point_drain.PointDrainError) as error:
        raise RefusedRun("selection", str(error), exit_code=2) from error
    queue = DurablePointQueue(root=Path(arguments.evidence_root) / "queue", binding=selection)
    point_drain.write_selection_document(
        evidence_root=arguments.evidence_root, binding=selection, catalog_path=catalog_path,
        extras=extras)
    return selection, queue, catalog_path


def station_processes(station_root: str, *, ps_runner=None) -> list[dict]:
    """Processes whose own argv declares exactly this attempt's station root.

    The station launcher is passed `task_evidence_root:=<station root>`, and the root is unique to
    one lease under this campaign's evidence root, so a match is this campaign's process and not a
    stranger's. Nothing is signalled here.
    """

    import subprocess

    runner = _default_ps_runner if ps_runner is None else ps_runner
    token = f"task_evidence_root:={station_root}"
    try:
        completed = runner(["ps", "-axo", "pid=,pgid=,command="])
    except (OSError, subprocess.SubprocessError):
        return []
    matches: list[dict] = []
    for line in (getattr(completed, "stdout", "") or "").splitlines():
        if token not in line or "so101_mujoco_task_station.launch.py" not in line:
            continue
        fields = line.split(None, 2)
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
            continue
        matches.append({"pid": int(fields[0]), "pgid": int(fields[1]), "command": fields[2]})
    return matches


def _default_ps_runner(command):
    import subprocess

    return subprocess.run(command, capture_output=True, text=True, timeout=30.0)


def stop_station_residue(station_root: str, *, ps_runner=None, signal_sender=None,
                         sleep=None, wait_s: float = 6.0) -> dict:
    """Stop a station that outlived the Worker that owned it, by exact identity, and report.

    A Worker killed by a signal never runs its own `finally`, so its station can survive it. The
    station is still this campaign's process - its argv names this attempt's station root - so it
    is stopped the way the station stack stops it: SIGINT to the launch's own process group, then
    SIGTERM, then SIGKILL, and never a group this campaign cannot name.
    """

    import signal as _signal
    import time as _time

    sender = (lambda pid, number: os.kill(pid, number)) if signal_sender is None else signal_sender
    sleeper = _time.sleep if sleep is None else sleep
    matches = station_processes(station_root, ps_runner=ps_runner)
    stopped, refused = [], []
    for entry in matches:
        leader = entry["pid"] == entry["pgid"]
        target = -entry["pgid"] if leader else entry["pid"]
        for number, grace in ((_signal.SIGINT, wait_s), (_signal.SIGTERM, wait_s / 2.0),
                              (_signal.SIGKILL, wait_s / 2.0)):
            try:
                sender(target, number)
            except ProcessLookupError:
                break
            except (PermissionError, OSError) as error:
                refused.append({"pid": entry["pid"], "error": f"{type(error).__name__}: {error}"})
                break
            sleeper(grace / 4.0)
            if not station_processes(station_root, ps_runner=ps_runner):
                break
        stopped.append(entry["pid"])
    remaining = station_processes(station_root, ps_runner=ps_runner)
    return {"station_root": station_root, "clear": not remaining, "stopped": stopped,
            "refused": refused, "remaining": [entry["pid"] for entry in remaining]}


def reconcile_station(station_root: str, *, ps_runner=None, signal_sender=None, sleep=None) -> dict:
    """Read this attempt's station back, and stop it if the Worker that owned it is gone."""

    readback = station_readback(station_root, ps_runner=ps_runner)
    if readback["clear"]:
        return readback
    stopped = stop_station_residue(station_root, ps_runner=ps_runner, signal_sender=signal_sender,
                                   sleep=sleep)
    after = station_readback(station_root, ps_runner=ps_runner)
    return {**after, "reconciled": stopped}


def station_readback(station_root: str, *, attempts: int = 6, sleep_s: float = 0.5,
                     ps_runner=None) -> dict:
    """Report whether anything still carries this attempt's station root.

    The Worker shuts its own station down; this is the campaign's independent readback of that
    claim. It signals nothing: a survivor is reported, and the drain stops rather than starting the
    next point on top of a station that is still alive.
    """

    matches: list[dict] = []
    for _attempt in range(int(attempts)):
        matches = station_processes(station_root, ps_runner=ps_runner)
        if not matches:
            break
        time.sleep(sleep_s)
    return {"station_root": station_root, "clear": not matches,
            "matches": [entry["pid"] for entry in matches[:8]]}


def campaign_verdict(*, spec, cleanup_complete, results, workers, served, refused,
                     points) -> str:
    """The campaign's own verdict for one route, as a pure function.

    PASS is the happy path only, and the happy path now includes the point set: cleanup proven
    complete, one result document per Worker spawn, **every** spawn recorded `ACTIVE`, at least the
    route's minimum number of served requests whose devices are exactly ``["mps"]``, no refused
    request at all, and `points["complete"]` - every selected point executed exactly once with its
    durable evidence, every `PASSED` point with its physical manifest, no duplicate attempt and no
    unselected point ever attempted.

    The point clause is the one the live gate was missing: without it a campaign that executed
    nothing at all reported `TWO_WORKER_CAMPAIGN_PASS`. A refused request - even a deliberate probe - still
    reads INCOMPLETE by construction.
    """

    if (cleanup_complete and workers and len(results) == len(workers)
            and all(worker["status"] == "ACTIVE" for worker in workers)
            and {worker["worker_id"] for worker in workers} >= set(spec.worker_ids)
            and served["count"] >= spec.minimum_served
            and served["devices"] == ["mps"]
            and not refused
            and bool(points.get("complete"))):
        return spec.pass_label
    return spec.incomplete_label
