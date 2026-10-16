"""Fixture builders for the phase-2 readback tests: a phase-1 sealed attempt and a processed output directory, written to tmp.

Not a test module. The data grading is a seam (`regrade`); the helpers here never run a QC."""

import hashlib
import json
from pathlib import Path

from so101_demo.act.processed_result import PROCESSED_KIND, PROCESSED_NAME, canonical

LEASE = dict(batch_id="b1", coordinator_epoch=1, worker_id="w00", worker_generation=1, point_id="scene-01",
             attempt_id="scene-01-lease-1", lease_generation=1, lease_issued_monotonic_s=10.0, lease_deadline_monotonic_s=900.0)
IDENTITY = dict(session_id="campaign-wave00-w00-g1", reset_epoch=1, attempt_id="scene-01-lease-1")
BINDING = ("qc_report_path", "qc_report_sha256", "inputs_sha256", "scope_sha256", "audit_manifest_sha256", "collection_mode")


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Processed:
    """One scene: `sealed` (phase 1), `output` (phase 2, attempt `number`) and the hashes that bind them."""

    def __init__(self, tmp_path, scene="scene-01", *, status="PASSED", number=1, valid=True, fault="none", wave_index=0):
        self.scene, self.number = scene, number
        self.wave_index = wave_index
        self.run = Path(tmp_path) / "run"
        attempt = scene + "-lease-1"
        self.lease = dict(LEASE, point_id=scene, attempt_id=attempt)
        self.identity = dict(IDENTITY, attempt_id=attempt)
        self.result_lease = {name: self.lease[name] for name in ("batch_id", "coordinator_epoch", "worker_id", "worker_generation", "point_id", "attempt_id", "lease_generation")}
        self.sealed = self.run / f"wave-{wave_index}/w00/g{wave_index + 1}/output/tasks/t-{scene}/attempts/{scene}/{attempt}/sealed"
        (self.sealed / "raw").mkdir(parents=True)
        (self.sealed / "dynamic").mkdir()
        (self.sealed / "dynamic/dynamic-execute-manifest.json").write_text("{}\n")
        self.receipt = json.dumps(dict(identity=self.identity, lease_identity=self.lease), sort_keys=True).encode() + b"\n"
        (self.sealed / "raw/recording-receipt.json").write_bytes(self.receipt)
        self.result = dict(kind="ACT_COLLECTION_RESULT", schema_version=3, lease_identity=self.result_lease, status=status,
                           teacher_execution_status="COMPLETED", teacher_task_result="PASS", act_data_status="PENDING_QC",
                           act_data_qc="NOT_RUN", export_eligible=False, episode_seal_sha256=None)
        raw = json.dumps(self.result, sort_keys=True).encode() + b"\n"
        (self.sealed / "result.json").write_bytes(raw)
        self.result_sha256, self.receipt_sha256 = sha(raw), sha(self.receipt)
        self.output = self.run / "processing" / scene / f"{attempt}-proc-{number}"
        self.output.mkdir(parents=True)
        self.out = self.output if fault == "none" else self.output / "out"
        (self.out / "episode").mkdir(parents=True, exist_ok=True)
        (self.out / "episode/seal.json").write_text("{}\n")
        self.scope, self.inputs = self.run / "scope.json", self.run / "inputs-manifest.json"
        self.scope.write_text("{}\n")
        self.inputs.write_text("{}\n")
        seal = sha((self.out / "episode/seal.json").read_bytes())
        self.document = dict(
            kind=PROCESSED_KIND, schema_version=1, task_id=f"{scene}-proc-{number}", scene_id=scene, proc_attempt=number,
            phase1_result_sha256=self.result_sha256, receipt_sha256=self.receipt_sha256, lease_identity=self.lease,
            identity=self.identity, status=status, processor_rc=0, diagnostic_fault=fault, artifacts={},
            act_data_status="VALID" if valid else "INVALID", act_data_reason=None if valid else "OFFLINE_PROCESSOR_INVALID: rc=3",
            act_data_qc="PASS" if valid else "NOT_RUN", episode_seal_sha256=seal,
            export_eligible=valid and status == "PASSED",
            qc_report_path="qc-report.json" if valid else None, qc_report_sha256="q" * 64 if valid else None,
            inputs_sha256="i" * 64 if valid else None, scope_sha256="s" * 64 if valid else None,
            audit_manifest_sha256="a" * 64 if valid else None, collection_mode="formal" if valid else None)
        self.write()

    def write(self, **override):
        self.document.update(override)
        (self.output / PROCESSED_NAME).write_bytes(canonical(self.document))

    def grader(self, **override):
        document = self.document

        def regrade(**kwargs):
            graded = dict(status="VALID", reason=None, qc=document["act_data_qc"], episode_sha256=document["episode_seal_sha256"],
                          binding={name: document[name] for name in BINDING})
            graded.update(override)
            return graded
        return regrade

    def row(self, *, pending=True, task_id=None):
        """The wave-verified case row the Host holds for this scene after phase 1 (`pending`: the Teacher half only)."""
        task_id = task_id or f"wave-{self.wave_index}-w00-{self.scene}"
        proof = dict(kind="ACT_CONTAINER_TASK_READBACK", status="PASS", result_status=self.result["status"],
                     teacher_execution_status="COMPLETED", teacher_task_result="PASS",
                     act_data_status="PENDING_QC" if pending else "INVALID",
                     act_data_reason=None if pending else "DYNAMIC_TARGET_UNREACHABLE", act_data_qc="NOT_RUN",
                     export_eligible=False, result_sha256=self.result_sha256, task_result_sha256="t" * 64,
                     location=str(self.sealed), scene_id=self.scene, task_id=task_id, worker_id="w00",
                     processing="PENDING" if pending else "NOT_PENDING",
                     receipt_sha256=self.receipt_sha256 if pending else None)
        return dict(scene_id=self.scene, worker_id="w00", location=str(self.sealed.parents[3]), task_id=task_id,
                    launch_id=f"wave-{self.wave_index}-w00-g{self.wave_index + 1}", proof=proof,
                    registration=str(self.run / "host" / task_id / "collected.json"),
                    owner_root=str(self.run / f"wave-{self.wave_index}/w00/g{self.wave_index + 1}"),
                    scope_path=str(self.scope), inputs_manifest=str(self.inputs))

    def verify(self, **kwargs):
        from so101_demo.act.processed_result import verify_processed_result

        kwargs.setdefault("regrade", self.grader())
        return verify_processed_result(self.output, sealed=self.sealed, scene_id=self.scene, result_sha256=self.result_sha256,
                                       receipt_sha256=self.receipt_sha256, scope=self.scope, inputs_manifest=self.inputs, **kwargs)


def echo_regrade(**kwargs):
    """A grader that agrees with whatever `processed-result.json` next to the data says (document versus files is test_processed_result)."""
    out = Path(kwargs["out"])
    path = out / PROCESSED_NAME if (out / PROCESSED_NAME).exists() else out.parent / PROCESSED_NAME
    document = json.loads(path.read_bytes())
    return dict(status="VALID", reason=None, qc=document["act_data_qc"], episode_sha256=document["episode_seal_sha256"],
                binding={name: document[name] for name in BINDING})


def echo_reader(output_dir, **kwargs):
    from so101_demo.act.processed_result import verify_processed_result

    return verify_processed_result(output_dir, regrade=echo_regrade, **kwargs)
