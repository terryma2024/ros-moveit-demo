"""Offline episode processor: a raw bag in, a sealed episode and a verdict out.

The processor opens the episode (frozen inputs, scope, lease), builds the `OfflineEngine` and the `OfflineRosSources`, and
feeds them from the record-only process's bag on a virtual clock (`replay.py`). Every gate, join, label, continuity and seal rule is the live one; the one substitution is the receipt instant of a
message: the record-only process's receipt (bag stamp mapped to the monotonic clock) stands in for the Recorder's.
`p2-substitution.md` lists every rule where that is not exact.

    act_offline_episode --bag <bag dir> --inputs <inputs-manifest.json> --out <attempt sealed dir> [--report <json>]

Output (all under --out): `episode/` (the sealed episode, same layout as the live Recorder's), `recorder-result.json`
(the engine's result, process-independent), `offline-qc-report.json` (the fresh-process QC) and the processor report.
Exit codes: 0 VALID and QC PASS, 3 INVALID data (the record is retained), 2 refused configuration, 4 infrastructure failure.
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RC_VALID, RC_CONFIG, RC_INVALID, RC_INFRA, RC_DIAGNOSTIC = 0, 2, 3, 4, 5
REPORT_SCHEMA = "SO101_OFFLINE_EPISODE_REPORT"
LEASE_FIELDS = ("batch_id", "coordinator_epoch", "worker_id", "worker_generation", "point_id", "attempt_id",
                "lease_generation", "lease_issued_monotonic_s", "lease_deadline_monotonic_s")
#: a bag clock map that disagrees with the sidecar's own (system, monotonic) pairs by more than this is not trusted
#: The clock map (bag system stamps to the monotonic clock) is built from two anchors read back to back (+-1 us measured) and
#: cross-checked against the scene-read pairs. The tightest receipt-ordering rule it feeds is a few milliseconds ("received before
#: request", the 100 ms join); observed residuals are 0.9 us and 2.8 us on the two real bags. 2 ms leaves a factor of 700 above the
#: observation and stays below the tightest rule.
CLOCK_RESIDUAL_LIMIT_NS = 2_000_000


class OfflineRefused(ValueError):
    """The request cannot be honoured (rc 2)."""


# ---- the clock map -------------------------------------------------------------------------------------------------

def scene_read_pairs(bag) -> list:
    """(system_ns, monotonic_ns) read back to back by the scene sidecar for each planning-scene read, from the bag itself."""
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String

    from .bag_io import read_messages
    from .raw_recorder import SCENE_READS_TOPIC

    pairs = []
    for _topic, _type, _stamp, data in read_messages(bag, topics=[SCENE_READS_TOPIC]):
        line = json.loads(deserialize_message(data, String).data)
        pairs.append((int(line["recorded_system_ns"]), int(line["recorded_monotonic_ns"])))
    return pairs


def load_loss_facts(bag, *, stats_file=None) -> dict:
    """What the record-only process knows about losses: the transport-layer total (the stats key, or for stats written before the key
    existed the line `ros2 bag record` printed into `bag-record.log` beside them; None when neither is there) and the number of
    planning-scene reads the sidecar made."""
    from .raw_recorder import transport_lost_from_log

    stats_path = Path(stats_file) if stats_file is not None else Path(bag).parent / "record-stats.json"
    lost, reads, by_topic, events = None, None, None, None
    stamps = None
    if stats_path.is_file():
        document = json.loads(stats_path.read_bytes())
        if type(document.get("transport_lost")) is int:
            lost = document["transport_lost"]
        by = document.get("transport_lost_by_topic")     # present only when the recorder ran with debug logging (C5)
        if type(by) is dict and all(type(k) is str and type(v) is int and v >= 0 for k, v in by.items()):
            by_topic = dict(sorted(by.items()))
            events = _loss_events(document.get("transport_lost_events"), by_topic,
                                  stats_path.parent / "bag-record.log")
        if isinstance(document.get("scene_reads"), dict) and type(document["scene_reads"].get("count")) is int:
            reads = document["scene_reads"]["count"]
        sidecar = stats_path.parent / "scene-reads.jsonl"
        if reads is not None and sidecar.is_file():
            stamps = _sidecar_read_stamps(sidecar)
        log = stats_path.parent / "bag-record.log"
        if lost is None and log.is_file():
            text = log.read_text(errors="replace")
            if "Recording stopped" in text:
                lost = transport_lost_from_log(text)
    return {"transport_lost": lost, "scene_reads_expected": reads, "transport_lost_by_topic": by_topic,
            "transport_lost_events": events, "scene_read_sidecar_stamps": stamps}


def _sidecar_read_stamps(path):
    """The simulation time (ns) at which each sidecar read answered, in file order; None when the file cannot be read as such."""
    stamps = []
    try:
        for line in Path(path).read_text().splitlines():
            if line:
                stamps.append(int(json.loads(line)["payload"]["response_ros_clock"]["sim_time_ns"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return stamps


def _loss_events(recorded, by_topic, log_path):
    """The per-event loss times: the stats' own list, or for stats written before it existed the debug lines of the recorder's log
    beside them. Accepted only when the last cumulative total of every topic equals the stats' per-topic figure; otherwise None (the
    scan then treats every reported loss as inside the window)."""
    from .raw_recorder import transport_lost_events_from_log

    events = recorded
    if events is None and log_path.is_file():
        events = transport_lost_events_from_log(log_path.read_text(errors="replace"))
    if type(events) is not list:
        return None
    last: dict = {}
    for item in events:
        if (type(item) is not dict or type(item.get("topic")) is not str or type(item.get("total")) is not int
                or type(item.get("log_time_ns")) is not int):
            return None
        last[item["topic"]] = max(last.get(item["topic"], 0), item["total"])
    return events if last == {k: v for k, v in by_topic.items() if v} else None


def load_clock_map(bag, *, stats_file=None):
    """(ClockMap, facts): the system->monotonic mapping, from the record-only process's anchors when it left them."""
    from .replay import ClockMap

    bag = Path(bag)
    anchors, source = [], None
    candidates = [Path(stats_file)] if stats_file is not None else [bag.parent / "record-stats.json"]
    for path in candidates:
        if path.is_file():
            document = json.loads(path.read_bytes())
            anchors = [document[key] for key in ("anchor_start", "anchor_end") if document.get(key)]
            source = str(path) if anchors else None
    pairs = scene_read_pairs(bag)
    facts = {"anchor_source": source, "scene_read_pairs": len(pairs)}
    if anchors:
        clock_map = ClockMap(anchors, source="anchors")
    elif pairs:
        clock_map = ClockMap([{"system_ns": pairs[0][0], "monotonic_ns": pairs[0][1]},
                              {"system_ns": pairs[-1][0], "monotonic_ns": pairs[-1][1]}], source="scene_reads")
        facts["anchor_source"] = "scene_reads"
    else:
        raise OfflineRefused("OFFLINE_CLOCK_ANCHORS_MISSING")
    residuals = [abs(clock_map.residual_ns(system, monotonic)) for system, monotonic in pairs]
    facts.update(map_source=clock_map.source, anchors=clock_map.anchors, drift_ppm=clock_map.drift_ppm,
                 max_residual_ns=max(residuals) if residuals else None)
    return clock_map, facts


# ---- inputs ----------------------------------------------------------------------------------------------------------

def read_lease(path) -> dict:
    """The nine lease fields from a JSON file: a lease document itself, or any document with a `lease` member
    (a live episode's `audit/episode.json`)."""
    try:
        document = json.loads(Path(path).read_bytes())
    except (OSError, ValueError) as error:
        raise OfflineRefused(f"OFFLINE_LEASE_UNREADABLE: {error}") from error
    if isinstance(document, dict) and isinstance(document.get("lease"), dict):
        document = document["lease"]
    if not isinstance(document, dict) or not set(LEASE_FIELDS) <= set(document):
        raise OfflineRefused("OFFLINE_LEASE_INCOMPLETE")
    return {name: document[name] for name in LEASE_FIELDS}


def teacher_start_draw(path):
    """R3-a: the start pose draw the Teacher applied and verified, read from its manifest (`teacher_diversity`), or None when the manifest
    is missing or has no diversity record. The Teacher's matched draw must be the one its values carry; a manifest that disagrees with
    itself is refused (``TEACHER_DIVERSITY_START_POSE_MISMATCH``) rather than recorded."""

    try:
        record = json.loads(Path(path).read_bytes()).get("teacher_diversity")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(record, dict):
        return None
    try:
        carried = record["values"]["start_pose"]["draw_index"]
    except (KeyError, TypeError):
        return None
    if record.get("start_pose_draw_index") != carried:
        raise ValueError("TEACHER_DIVERSITY_START_POSE_MISMATCH")
    return carried


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_json(path: Path, document: dict) -> None:
    path = Path(path)
    staging = path.with_name(f".{path.name}.{os.getpid()}.pending")
    with open(staging, "wb") as stream:
        stream.write((json.dumps(document, sort_keys=True, indent=1, default=str, allow_nan=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, path)


def release_memory() -> None:
    """Give back what the replay and the seal no longer need, before the fresh-process QC starts.

    The engine, its episode, the sources and the replay node reference each other, so they go with a collection, not with the last
    name; the allocator is then asked to return the freed pages (the replay's churn leaves most of them as free space inside the heap).
    Nothing the report or the QC reads lives in them."""
    gc.collect()
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):   # not glibc: the collection above still ran
        pass


def run_independent_qc(episode_root, *, scope, inputs_manifest, teacher_manifest, output, ignore_scene_colors=False) -> dict:
    """The sealed episode's QC in a fresh interpreter: {"status": PASS|FAIL|ERROR, "reason", "rc", ...}."""
    argv = [sys.executable, "-m", "so101_demo.act.offline.independent_qc", "--episode", str(episode_root), "--scope", str(scope),
            "--inputs-manifest", str(inputs_manifest), "--output", str(output)]
    if teacher_manifest is not None:
        argv += ["--teacher-manifest", str(teacher_manifest)]
    if ignore_scene_colors:
        argv += ["--diagnostic-ignore-scene-colors"]
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=900)
    try:
        line = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        line = {"status": "ERROR", "reason": (completed.stderr or completed.stdout or "NO_OUTPUT")[-500:]}
    line["rc"] = completed.returncode
    return line


_PIPELINE_MODULES = (
    "so101_demo.act.offline.sources", "so101_demo.act.offline.engine", "so101_demo.ros.recorder_data_side", "so101_demo.ros.data_source_binding",
    "so101_demo.adapters.act.ros_episode_physics", "so101_demo.adapters.act.scene_state", "so101_demo.adapters.act.ros_observation",
    "so101_demo.adapters.act.controller_reference_observer", "so101_demo.backends.mujoco.observer",
    "so101_demo.act.live_physical_audit", "so101_demo.act.episode_assembly", "so101_demo.act.continuous_capture",
    "so101_demo.act.recorder", "so101_demo.act.lossless_recorder", "so101_demo.act.synchronizer",
    "so101_demo.act.episode_audit", "so101_demo.act.episode_qc")


def preload_pipeline() -> None:
    """Import the pipeline before the virtual clock is installed, so no module binds a replay clock at import."""
    import importlib

    for name in _PIPELINE_MODULES:
        try:
            importlib.import_module(name)
        except ImportError:
            pass


@contextlib.contextmanager
def _colors_ignored(enabled):
    """DIAGNOSTIC ONLY: compare scene geometry without the object colours (the Teacher's ACM-only apply drops the attached
    cup's colour from every later read). The result is labelled DIAGNOSTIC_*, exit code 5; fresh-process QC still compares colours."""
    if not enabled:
        yield
        return
    from unittest import mock

    from ...control.planning_scene import task_scene

    real = task_scene.normalized_scene_geometry

    def without_colors(scene):
        geometry = real(scene)
        geometry["colors"] = []
        return geometry

    with mock.patch.object(task_scene, "normalized_scene_geometry", without_colors):
        yield


# ---- the processor -----------------------------------------------------------------------------------------------------

def _inputs_rig(inputs_manifest):
    """The rig the frozen inputs bind. A manifest that cannot be read here is refused by the policy load that follows; the rig
    is then the default (v1), which only the bag's own topics can contradict."""
    from ..frozen_runtime_inputs import load_frozen_rig
    from ..rig_profile import DEFAULT_RIG

    try:
        return load_frozen_rig(inputs_manifest)
    except (OSError, ValueError):
        return DEFAULT_RIG


def process_bag(bag, out, *, inputs_manifest, lease, scope=None, teacher_manifest=None, stats_file=None,
                episode_factory=None, sources_factory=None, policy=None, qc_runner=None, camera_repair=False,
                teacher_clock_repair=False, ignore_scene_colors=False, qc_output=None) -> dict:
    """Build the episode of `bag` under `out/episode`. Returns the processor report (also the caller's verdict)."""
    import time as _time

    from .replay import _REAL

    wall_began = _REAL["perf_counter"]()
    bag, out, inputs_manifest = Path(bag), Path(out), Path(inputs_manifest)
    if not out.is_absolute() or ".." in out.parts:
        raise OfflineRefused("OFFLINE_OUT_INVALID")
    if (out / "episode").exists() or (out / "recorder-result.json").exists():
        raise OfflineRefused("OFFLINE_OUTPUT_EXISTS")
    from .bag_io import bag_info
    from .scan import scan_bag

    info = bag_info(bag)
    clock_map, clock_facts = load_clock_map(bag, stats_file=stats_file)
    rig = _inputs_rig(inputs_manifest)
    scan_began = _REAL["perf_counter"]()
    loss_facts = load_loss_facts(bag, stats_file=stats_file)
    scan = scan_bag(bag, info=info, rig=rig, **loss_facts)
    scan_s = _REAL["perf_counter"]() - scan_began
    reasons = list(scan["reasons"])
    if clock_facts["max_residual_ns"] is not None and clock_facts["max_residual_ns"] > CLOCK_RESIDUAL_LIMIT_NS:
        reasons.append(f"OFFLINE_CLOCK_MAP_INCONSISTENT: residual_ns={clock_facts['max_residual_ns']}")
    timeline = scan["timeline"]
    report = {"schema": REPORT_SCHEMA, "schema_version": 1, "bag": {"path": str(bag), "message_count": info["message_count"],
                                               "duration_ns": info["duration_ns"], "counts": scan["counts"]},
              "clock": clock_facts, "timeline": timeline, "continuity": scan["continuity"], "camera_grid": scan.get("camera_grid"), "window_start": scan.get("window_start"), "scan_reasons": list(scan["reasons"]),
              "inputs_manifest": str(inputs_manifest), "engine": None, "qc": {"status": "NOT_RUN"}, "episode": None}
    identity = timeline["identity"]
    out.mkdir(parents=True, exist_ok=True)
    if identity is None or any(identity.get(key) in (None, "") for key in ("session_id", "reset_epoch", "attempt_id")):
        report.update(verdict="INVALID", rc=RC_INVALID, reasons=reasons + ["OFFLINE_NO_TEACHER_IDENTITY"])
        report["timing"] = {"wall_s": _REAL["perf_counter"]() - wall_began, "scan_s": scan_s}
        return report
    if lease.get("attempt_id") != identity["attempt_id"]:
        raise OfflineRefused("OFFLINE_LEASE_ATTEMPT_MISMATCH")
    if scan.get("topic_loss") is not None:
        # phase C: the gate document sits beside the episode; the QC binds it to its verdict
        from .. import topic_loss as gate

        gate_document = gate.build_document(
            identity={key: identity[key] for key in ("session_id", "reset_epoch", "attempt_id")},
            window=scan["topic_loss"]["window"], transport_lost=scan["topic_loss"]["transport_lost"],
            topics=scan["topic_loss"]["topics"], reasons=list(scan["reasons"]))
        gate_bytes = gate.canonical(gate_document)
        (out / gate.DOCUMENT_NAME).write_bytes(gate_bytes)
        report["topic_loss"] = {"status": gate_document["status"], "lost_in_window": gate_document["lost_in_window"],
                                "transport_lost": gate_document["transport_lost"], "sha256": hashlib.sha256(gate_bytes).hexdigest()}

    from ..episode_open import open_recorder_episode
    from ..frozen_runtime_inputs import load_recorder_frozen_policy
    from ..collection_scope import build_collection_scope, write_collection_scope
    from ..diagnostic_episode_inputs import verify_frozen_inputs
    from ..teacher_event_stream import StreamIdentity
    from .engine import OfflineEngine
    from .replay import BagStream, CameraGridRepair, ReplayNode, TeacherClockRepair, VirtualClock, virtual_time

    if scope is None:
        frozen = verify_frozen_inputs(inputs_manifest)
        if "scene_manifest" in frozen:
            # a set that binds a scene list has no single scene to derive: the caller names the scope of the row it ran
            raise OfflineRefused("OFFLINE_SCOPE_REQUIRED")
        anchor = frozen["roles"]["anchor_scene"]["identity"]
        document = build_collection_scope(frozen["mode"], scene_id=anchor["scene_id"], seed=anchor["seed"],
                                          inputs_sha256=frozen["inputs_sha256"])
        scope = out / "episode-scope.json"
        write_collection_scope(document, scope)
    policy = (load_recorder_frozen_policy(inputs_manifest) if policy is None else dict(policy))
    stream_identity = StreamIdentity(identity["session_id"], identity["reset_epoch"], identity["attempt_id"])
    episode_root = out / "episode"
    options = SimpleNamespace(session_id=identity["session_id"], expected_reset_epoch=identity["reset_epoch"],
                              episode_root=episode_root,
                              evidence_root=out / "offline-evidence" / "dynamic", episode_scope=Path(scope),
                              episode_inputs_manifest=inputs_manifest, fault="none", **lease,
                              # R3-a: the start pose draw the Teacher applied, for the episode identity of a schema 6 freeze
                              start_pose_draw=teacher_start_draw(
                                  (out / "dynamic" / "dynamic-execute-manifest.json") if teacher_manifest is None else teacher_manifest))
    stream = BagStream(bag, clock_map)
    first = stream.peek()
    if first is None:
        report.update(verdict="INVALID", rc=RC_INVALID, reasons=reasons + ["OFFLINE_BAG_EMPTY"])
        return report
    clock = VirtualClock(clock_map, first.monotonic_ns)
    preload_pipeline()
    replay_began = _REAL["perf_counter"]()
    engine = episode = None
    with virtual_time(clock), tempfile.TemporaryDirectory(prefix="so101-offline-") as work, _colors_ignored(ignore_scene_colors):
        try:
            repair = CameraGridRepair() if camera_repair else None
            window_start = scan.get("window_start")
            clock_repair = TeacherClockRepair() if teacher_clock_repair else None
            node = ReplayNode(stream, clock, camera_repair=repair, teacher_clock_repair=clock_repair,
                              start_at_stamp_ns=None if window_start is None else window_start["bag_stamp_ns"],
                              camera_topics=rig.image_topics)
            episode = (episode_factory or (lambda o: open_recorder_episode(o, offline=True)))(options)
            if sources_factory is None:
                from .sources import OfflineRosSources

                sources = OfflineRosSources(node, episode, options, policy=policy,
                                            final_normal_stop_seq=timeline.get("final_normal_stop_seq"), rig=rig)
            else:
                sources = sources_factory(node, episode, options, policy)
            engine = OfflineEngine(episode=episode, sources=sources, policy=policy, identity=stream_identity,
                                   result_file=Path(work) / "recorder-result.json",
                                   clock=clock.monotonic, sleep=clock.advance, rig=rig, readback_after_seal=False)
            # a DIAGNOSTIC run looks past the camera defect: the scan names it, the engine is not told
            rc = engine.process(node, preset_reasons=[r for r in reasons
                                                       if not (camera_repair and r.startswith("OFFLINE_CAMERA_"))])
            repaired = None if repair is None else {"snapped": repair.snapped, "inserted": repair.inserted}
            clock_repaired = None if clock_repair is None else clock_repair.repaired
            result = json.loads((Path(work) / "recorder-result.json").read_bytes())
            _write_json(out / "recorder-result.json", result)
            delivered = dict(node.delivered_by_topic)
            virtual_s = (clock.now_ns - first.monotonic_ns) / 1e9
            passes = engine.passes
        finally:
            stream.close()
    replay_s = _REAL["perf_counter"]() - replay_began
    drained = {topic: delivered.get(topic, 0) for topic in scan["counts"]}
    report["engine"] = {"status": result["status"], "rc": rc, "reasons": result["reasons"], "reason_count": result["reason_count"],
                        "collection_start_s": result["collection_start_s"], "window": result["window"],
                        "sources": result["sources"], "event_stream": {key: result["event_stream"][key] for key in
                                                                         ("accepted", "last_seq", "terminal", "stop_seen")},
                        "seal": result["seal"], "passes": passes, "delivered": drained}
    verdict, reasons_out = ("VALID" if rc == RC_VALID else "INVALID"), [item["reason"] for item in result["reasons"]]
    # the replay ends at the Teacher's terminal event plus the tail: what the bag holds beyond that was never played, by design
    report["bag"]["not_played"] = {topic: count - drained[topic] for topic, count in scan["counts"].items() if count != drained[topic]}
    # the fresh-process QC runs next, next to this process: drop the replay's objects first
    engine = episode = sources = node = None
    release_memory()
    qc_began = _REAL["perf_counter"]()
    if verdict == "VALID":
        runner = qc_runner or (lambda root, **kw: run_independent_qc(root, ignore_scene_colors=ignore_scene_colors, **kw))
        teacher = (out / "dynamic" / "dynamic-execute-manifest.json") if teacher_manifest is None else Path(teacher_manifest)
        qc = runner(episode_root, scope=scope, inputs_manifest=inputs_manifest, teacher_manifest=teacher,
                    output=(out / "offline-qc-report.json") if qc_output is None else Path(qc_output))
        report["qc"] = qc
        if qc.get("status") != "PASS":
            verdict = "INVALID"
            reasons_out.append("OFFLINE_QC_" + str(qc.get("status")) + ": " + str(qc.get("reason", ""))[:300])
    if verdict == "VALID":
        # Teacher policy v3: the process summary, the policy version and the provenance are copied beside the sealed episode (never
        # into it). The data verdict is already decided; a manifest that cannot be copied is reported, not hidden.
        try:
            from ..teacher_process import write_metadata

            metadata = write_metadata(teacher, out)
            report["teacher_process"] = None if metadata is None else {
                "teacher_execution_policy_version": metadata["teacher_execution_policy_version"],
                "cup_pose_source": metadata["cup_pose_source"], "verdict_source": metadata["verdict_source"],
                "summary_schema": metadata["teacher_process_summary_schema"],
                "complete": metadata["teacher_process_summary"]["complete"],
                "flags": metadata["teacher_process_summary"]["flags"]}
        except (OSError, ValueError) as error:
            report["teacher_process"] = {"error": str(error)[:300]}
    report["episode"] = {"root": str(episode_root), "seal_sha256": None if result["seal"] is None else result["seal"]["sha256"]}
    report.update(verdict=verdict, rc=RC_VALID if verdict == "VALID" else RC_INVALID, reasons=reasons_out)
    if camera_repair or teacher_clock_repair or ignore_scene_colors:
        # never evidence: the verdict names what the run would have been, the exit code is never 0 or 3
        report.update(verdict="DIAGNOSTIC_" + verdict, rc=RC_DIAGNOSTIC, diagnostic={"camera_grid_repair": repaired, "teacher_clock_repair": clock_repaired,
                                                                 "ignore_scene_colors": ignore_scene_colors})
    report["timing"] = {"wall_s": _REAL["perf_counter"]() - wall_began, "scan_s": scan_s, "replay_s": replay_s,
                        "qc_s": _REAL["perf_counter"]() - qc_began, "virtual_s": virtual_s}
    return report


# ---- the command line ----------------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="act_offline_episode", description=__doc__.split("\n\n")[0])
    parser.add_argument("--bag", type=Path, required=True, help="the rosbag2 MCAP directory (raw/bag)")
    parser.add_argument("--inputs", type=Path, required=True, help="the frozen inputs-manifest.json of the run")
    parser.add_argument("--out", type=Path, required=True, help="the attempt's sealed directory; <out>/episode is created")
    parser.add_argument("--report", type=Path, help="processor report JSON (default <out>/offline-processor-report.json)")
    parser.add_argument("--lease", type=Path, required=True,
                        help="JSON with the attempt's nine lease fields, or a document with a `lease` member (episode.json)")
    parser.add_argument("--scope", type=Path, help="the run's episode-scope.json (default: derived from the inputs and written)")
    parser.add_argument("--teacher-manifest", type=Path, help="default <out>/dynamic/dynamic-execute-manifest.json")
    parser.add_argument("--diagnostic-camera-repair", action="store_true",
                        help="DIAGNOSTIC ONLY: re-stamp camera frames within 2.5 ms onto the 100 ms grid and fill up to two missing "
                             "frames; the result is labelled DIAGNOSTIC_*, exit code 5, and is not evidence")
    parser.add_argument("--diagnostic-teacher-clock-repair", action="store_true",
                        help="DIAGNOSTIC ONLY: replace a Teacher scene-operation clock reading that lags /clock by more than 30 ms; "
                             "the result is labelled DIAGNOSTIC_*, exit code 5, and is not evidence")
    parser.add_argument("--diagnostic-ignore-scene-colors", action="store_true",
                        help="DIAGNOSTIC ONLY: compare planning-scene geometry without object colours; labelled DIAGNOSTIC_*, exit 5")
    parser.add_argument("--qc-output", type=Path,
                        help="where the fresh-process QC report is written (default <out>/offline-qc-report.json); the run path "
                             "puts it at the attempt's qc-report.json for the ResultStore")
    parser.add_argument("--record-stats", type=Path, help="the record-only process's record-stats.json (default beside the bag)")
    return parser


def main(arguments=None, **injected) -> int:
    try:
        options = build_parser().parse_args(arguments)
    except SystemExit as error:
        return RC_CONFIG if error.code else RC_VALID
    report_path = options.report or (options.out / "offline-processor-report.json")
    try:
        lease = read_lease(options.lease)
        report = process_bag(options.bag, options.out, inputs_manifest=options.inputs, lease=lease, scope=options.scope,
                             teacher_manifest=options.teacher_manifest, stats_file=options.record_stats,
                             camera_repair=options.diagnostic_camera_repair,
                             teacher_clock_repair=options.diagnostic_teacher_clock_repair,
                             ignore_scene_colors=options.diagnostic_ignore_scene_colors, qc_output=options.qc_output, **injected)
    except OfflineRefused as error:
        print(f"status=ERROR failure=OFFLINE_REFUSED message={error}", file=sys.stderr, flush=True)
        return RC_CONFIG
    except Exception as error:   # noqa: BLE001 - an infrastructure defect is never reported as a data verdict
        import traceback

        print(f"status=ERROR failure=OFFLINE_INFRASTRUCTURE message={type(error).__name__}: {error}", file=sys.stderr, flush=True)
        traceback.print_exc()
        return RC_INFRA
    _write_json(report_path, report)
    print(f"status={report['verdict']} rc={report['rc']} report={report_path}", flush=True)
    return report["rc"]


if __name__ == "__main__":
    raise SystemExit(main())
