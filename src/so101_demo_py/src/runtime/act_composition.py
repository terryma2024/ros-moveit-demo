"""Task 14: compose a search-to-ACT session, and refuse an execute run that is not fully equipped.

Planning a session is cheap and reversible; executing one moves the arm. So the two are gated differently:
`dry_run` and `plan_only` need only a mode and an evidence root, while `execute` refuses unless every
artifact it will lean on is present and verifiable.
"""

from __future__ import annotations

from pathlib import Path

MODES = ("dry_run", "plan_only", "execute")
_EXECUTE_INPUTS = (("bundle_path", "ACT_EXECUTE_BUNDLE_REQUIRED"),
                   ("calibration_path", "ACT_EXECUTE_CALIBRATION_REQUIRED"),
                   ("policy_path", "ACT_EXECUTE_POLICY_REQUIRED"),
                   ("activation_receipt", "ACT_EXECUTE_ACTIVATION_REQUIRED"),
                   ("runtime_config", "ACT_EXECUTE_RUNTIME_CONFIG_REQUIRED"))


def _require_file(value, code: str) -> str:
    if value is None or not str(value):
        raise ValueError(code)
    path = Path(value)
    if not path.is_file() or path.is_symlink():
        raise ValueError(code)
    return str(path)


def build_act_session_composition(*, mode: str, context, worker_port, inference, evidence_root,
                                  bundle_path=None, calibration_path=None, policy_path=None,
                                  activation_receipt=None, runtime_config=None) -> dict:
    """Build the composition the session runs under, with the mode deciding what must be proven."""

    if mode not in MODES:
        raise ValueError("ACT_SESSION_MODE_INVALID")
    if not callable(getattr(worker_port, "request", None)):
        raise ValueError("SESSION_WORKER_PORT_REQUIRED")
    if not callable(getattr(inference, "submit", None)):
        raise ValueError("SESSION_INFERENCE_REQUIRED")
    root = Path(evidence_root)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or ".." in root.parts:
        raise ValueError("ACT_SESSION_EVIDENCE_ROOT_INVALID")

    composition = {"mode": mode, "evidence_root": str(root), "effects": mode == "execute",
                   "context": context, "worker_port": worker_port, "inference": inference,
                   "artifacts": {}}
    if mode != "execute":
        # planning paths deliberately require no model: they must stay runnable before one exists
        return composition

    supplied = {"bundle_path": bundle_path, "calibration_path": calibration_path,
                "policy_path": policy_path, "activation_receipt": activation_receipt,
                "runtime_config": runtime_config}
    for field, code in _EXECUTE_INPUTS:
        composition["artifacts"][field] = _require_file(supplied[field], code)

    from so101_demo.act.bundle import load_bundle
    from so101_demo.act.runtime_config import load_runtime_config

    composition["bundle"] = load_bundle(composition["artifacts"]["bundle_path"])
    composition["runtime_settings"] = load_runtime_config(composition["artifacts"]["runtime_config"])
    return composition
