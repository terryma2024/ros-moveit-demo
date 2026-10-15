"""Phase-2 verification on the Host: the combined per-scene proof of both phases.

`verify_processing(root, waves, scene_ids)` joins, for every scene of the frozen list:

* the phase-1 proof (the wave-verified readback of the Teacher record and the recording receipt),
* the phase-2 proof (the readback of `processed-result.json`, `act.processed_result`), found through the phase-2 scheduler's
  `host/processing-journal.jsonl` and `host/processing-result.json`, and
* the list of every processing attempt that the journal records, failed ones included.

A scene always appears, in the frozen order. Its `state` is

    PROCESSED         a final processing attempt whose processed result read back (the data verdict is VALID or INVALID)
    FINAL_AT_PHASE1   the phase-1 record is already final (a pre-motion Teacher failure that recorded nothing): nothing to process
    FAULT             processing was refused, retries were exhausted, or the processed result or the records disagree
    MISSING           no evidence: phase 1 never recorded the scene, phase 2 ran out of time, or the scene was never processed

`FAULT` and `MISSING` are never a pass: their `verdict` carries `PROCESSING_FAULT` / `PROCESSING_MISSING` as the data status, the gates
see no evidence, and the qualification counts the scene in the denominator.

The journal is the authority on attempts; the summary is checked against it, and the processed result is read back from its files
(never from a hash the summary claims). Nothing here writes.
"""

import hashlib
import json
from pathlib import Path

from so101_demo.act.processed_result import REFUSAL as PROCESSED_REFUSAL, verify_processed_result
from so101_demo.runtime.container_campaign.readback_pool import resolve_readback_workers, run_readbacks

STATES = ("PROCESSED", "FINAL_AT_PHASE1", "FAULT", "MISSING")
COMBINED_KIND = "act_collection_combined_proof"
CAMPAIGN_RESULT_KIND = "act_collection_campaign_result"
SUMMARY_NAME = "processing-result.json"
JOURNAL_NAME = "processing-journal.jsonl"
_JOURNAL_KIND = "ACT_PROCESSING_JOURNAL"
_FINAL = ("VALID", "INVALID")
_TEACHER = ("teacher_execution_status", "teacher_task_result")
_REASON_CHARS = 300


def _file_ref(path):
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())


def read_journal(path):
    """The journal's lines in order, or None when there is none. Sequence numbers must run 1, 2, 3, ... without a gap."""
    path = Path(path)
    if not path.is_file():
        return None
    events = []
    try:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            event = json.loads(line)
            if (type(event) is not dict or event.get("kind") != _JOURNAL_KIND or event.get("seq") != number
                    or type(event.get("event")) is not str):
                raise ValueError("line")
            events.append(event)
    except (OSError, ValueError, UnicodeError) as error:
        raise ValueError("PROCESSING_JOURNAL_INVALID") from error
    return events


def read_summary(path):
    path = Path(path)
    if not path.is_file():
        return None
    try:
        summary = json.loads(path.read_bytes())
        scenes = {item["scene_id"]: item for item in summary["scenes"]}
        if type(summary) is not dict or len(scenes) != len(summary["scenes"]):
            raise ValueError("scenes")
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        raise ValueError("PROCESSING_SUMMARY_INVALID") from error
    return scenes


def _attempts(events):
    """`{scene_id: [attempt]}` from the dispatches and results of the journal, plus the scenes with a fault or missing event."""
    attempts, faults, missing = {}, set(), set()
    for event in events or ():
        kind, scene = event["event"], event.get("scene_id")
        if kind == "dispatch":
            attempts.setdefault(scene, []).append(dict(task_id=event["task_id"], proc_attempt=event["proc_attempt"],
                processor_id=event["processor_id"], launch_generation=event["launch_generation"],
                output_dir=event["output_dir"], outcome="NO_RESULT", reason=None, processor_rc=None))
        elif kind == "result":
            for item in reversed(attempts.get(scene, ())):
                if item["task_id"] == event["task_id"] and item["outcome"] == "NO_RESULT":
                    item.update(outcome=event["outcome"], reason=event.get("reason"), processor_rc=event.get("processor_rc"))
                    break
        elif kind == "scene_fault":
            faults.add(scene)
        elif kind == "scene_missing":
            missing.add(scene)
    return attempts, faults, missing


def _teacher(proof):
    return dict(status=proof["result_status"], **{name: proof[name] for name in _TEACHER})


def _verdict(proof, *, data=None, state=None):
    """The final per-scene verdict: the Teacher half from phase 1, the data half from phase 2 (or an explicit no-evidence)."""
    if proof is None:
        teacher = dict(status="NOT_RECORDED", teacher_execution_status=None, teacher_task_result=None)
    else:
        teacher = _teacher(proof)
    if data is not None:
        fields = {name: data[name] for name in ("act_data_status", "act_data_reason", "act_data_qc", "export_eligible")}
    elif state == "FINAL_AT_PHASE1":
        fields = {name: proof[name] for name in ("act_data_status", "act_data_reason", "act_data_qc", "export_eligible")}
    else:
        fields = dict(act_data_status="PROCESSING_FAULT" if state == "FAULT" else "PROCESSING_MISSING", act_data_reason=None,
                      act_data_qc="NOT_RUN", export_eligible=False)
    return {**teacher, **fields}


def _record(row, state, reason, *, phase2=None, attempts=()):
    proof = None if row is None else row["proof"]
    keys = ("worker_id", "task_id", "launch_id", "location", "registration", "owner_root", "scope_path", "inputs_manifest")
    identity = {key: None if row is None else row[key] for key in keys}
    reason = None if reason is None else str(reason)[:_REASON_CHARS]
    verdict = _verdict(proof, data=phase2, state=state)
    if state in ("FAULT", "MISSING") and reason is not None and verdict["act_data_reason"] is None:
        verdict["act_data_reason"] = reason
    return dict(state=state, reason=reason, **identity, phase1=proof, phase2=phase2, attempts=list(attempts), verdict=verdict)


def _under(root, scene, output_dir):
    try:
        path = Path(output_dir)
        return path.is_absolute() and ".." not in path.parts and path.parent == Path(root) / "processing" / scene
    except TypeError:
        return False


def _default_reader(output_dir, **kwargs):
    return verify_processed_result(output_dir, **kwargs)


def verify_processing(root, waves, scene_ids, *, readback_workers=None, readback_timeout_s=None, processed_reader=None):
    """The combined proof of every scene in `scene_ids`, in that order; see the module docstring.

    `waves` are the verified phase-1 wave records (`case_results` rows with their readback proof). `processed_reader` is a seam
    (default: `act.processed_result.verify_processed_result`, in worker processes when more than one readback worker is allowed)."""
    root = Path(root)
    events = read_journal(root / "host" / JOURNAL_NAME)
    summary = read_summary(root / "host" / SUMMARY_NAME)
    attempts, faulted, absent = _attempts(events)
    rows = {row["scene_id"]: row for wave in waves for row in wave["case_results"]}
    if len(rows) != sum(len(wave["case_results"]) for wave in waves):
        raise ValueError("PROCESSING_PHASE1_ROWS_INVALID")
    entries, jobs = {}, []
    for scene in scene_ids:
        row = rows.get(scene)
        if row is None:
            entries[scene] = _record(None, "MISSING", "PHASE1_NOT_RECORDED")
            continue
        proof = row["proof"]
        if proof.get("processing") != "PENDING":
            entries[scene] = _record(row, "FINAL_AT_PHASE1", None)
            continue
        made = attempts.get(scene, [])
        if summary is None:
            reason = "PROCESSING_NOT_RUN" if events is None else "PROCESSING_SUMMARY_MISSING"
            entries[scene] = _record(row, "MISSING", reason, attempts=made)
            continue
        item = summary.get(scene)
        if item is None:
            entries[scene] = _record(row, "MISSING", "PROCESSING_NOT_QUEUED", attempts=made)
        elif item.get("status") == "MISSING":
            consistent = scene in absent
            entries[scene] = _record(row, "MISSING" if consistent else "FAULT",
                                     item.get("reason") if consistent else "PROCESSING_RECORD_MISMATCH", attempts=made)
        elif item.get("status") == "FAULT":
            consistent = scene in faulted
            reason = f"{item.get('fault')}: {item.get('reason')}" if consistent else "PROCESSING_RECORD_MISMATCH"
            entries[scene] = _record(row, "FAULT", reason, attempts=made)
        elif item.get("status") == "FINAL":
            last = made[-1] if made else None
            if (last is None or last["outcome"] != item.get("outcome") or last["outcome"] not in _FINAL
                    or last["output_dir"] != item.get("output_dir") or not _under(root, scene, last["output_dir"])
                    or item.get("attempts") != len(made)):
                entries[scene] = _record(row, "FAULT", "PROCESSING_RECORD_MISMATCH", attempts=made)
            else:
                jobs.append((scene, row, made, last["output_dir"]))
        else:
            entries[scene] = _record(row, "FAULT", "PROCESSING_RECORD_MISMATCH", attempts=made)
    for (scene, row, made, output_dir), answer in zip(jobs, _read_back(jobs, readback_workers, readback_timeout_s,
                                                                      processed_reader or _default_reader), strict=True):
        if isinstance(answer, Exception):
            reason = str(answer) or PROCESSED_REFUSAL
            entries[scene] = _record(row, "FAULT", reason if reason.startswith(PROCESSED_REFUSAL) else f"{PROCESSED_REFUSAL}: {reason}",
                                     attempts=made)
        else:
            entries[scene] = _record(row, "PROCESSED", None, phase2=answer, attempts=made)
    scenes = [dict(scene_id=scene, **entries[scene]) for scene in scene_ids]
    counts = {state: sum(1 for item in scenes if item["state"] == state) for state in STATES}
    return dict(schema_version=1, kind=COMBINED_KIND, scene_count=len(scenes), counts=counts,
                missing_evidence=[item["scene_id"] for item in scenes if item["phase1"] is None],
                processing=dict(summary=_file_ref(root / "host" / SUMMARY_NAME), journal=_file_ref(root / "host" / JOURNAL_NAME)),
                scenes=scenes)


def _read_back(jobs, workers, timeout_s, reader):
    """The processed readback of every job, in job order: the record, or the `ValueError` that refused it."""
    arguments = [dict(sealed=Path(row["proof"]["location"]), scene_id=scene, result_sha256=row["proof"]["result_sha256"],
                      receipt_sha256=row["proof"]["receipt_sha256"], scope=Path(row["scope_path"]),
                      inputs_manifest=Path(row["inputs_manifest"])) for scene, row, _made, _output in jobs]
    workers = resolve_readback_workers(workers)
    if reader is not _default_reader or workers == 1 or len(jobs) < 2:
        answers = []
        for (_scene, _row, _made, output_dir), kwargs in zip(jobs, arguments, strict=True):
            try:
                answers.append(reader(output_dir, **kwargs))
            except (OSError, ValueError, TypeError, KeyError) as error:
                answers.append(error if isinstance(error, ValueError) else ValueError(PROCESSED_REFUSAL))
        return answers
    pooled = [dict(scene_id=scene, registration=row["registration"], scope=row["scope_path"],
                   inputs_manifest=row["inputs_manifest"],
                   processing=dict(output_dir=output_dir, **{key: (str(value) if isinstance(value, Path) else value)
                                                             for key, value in kwargs.items() if key not in ("scope", "inputs_manifest")}))
              for (scene, row, _made, output_dir), kwargs in zip(jobs, arguments, strict=True)]
    return run_readbacks(pooled, workers=workers, timeout_s=timeout_s)


def build_campaign_result(campaign_id, scene_count, combined):
    """`host/campaign-result.json` of a two-phase campaign: every scene's combined record and the processing files it came from."""
    return dict(schema_version=2, kind=CAMPAIGN_RESULT_KIND, campaign_id=campaign_id, scene_count=scene_count,
                counts=combined["counts"], missing_evidence=combined["missing_evidence"], processing=combined["processing"],
                scenes=combined["scenes"])
