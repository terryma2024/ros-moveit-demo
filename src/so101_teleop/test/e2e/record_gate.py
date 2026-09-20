"""Registered execution gate for the unified webapp implementation task.

Every Python and Bun gate of this task runs through :func:`run_gate`. One call proves,
before it starts anything, that the interpreter it was handed really is the interpreter
that runs, and that ``tempfile.gettempdir()`` resolves inside a freshly created scratch
directory owned by this invocation. The invocation directory itself is retained under
``<root>/gates/<uuid>/`` with argv, stdout, stderr, elapsed time and exit code.

The registered root and the NVMe requirement come from an operator-registered policy
object whose bytes are frozen in the dispatching shell. The CLI deliberately offers no
host or NVMe override flags; a drifted policy object fails the next gate closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

POLICY_REFERENCE_ENV = "SO101_GATE_POLICY"
POLICY_DIGEST_ENV = "SO101_GATE_POLICY_SHA256"
NVME_EVIDENCE_ROOT = Path("/data/work/so101-evidence")
PROOF_PROGRAM = "import sys, tempfile; print(sys.executable); print(tempfile.gettempdir())"
POLICY_FIELDS = ("execution_host", "task_root", "require_ai_station_nvme")


@dataclass(frozen=True)
class GatePolicy:
    execution_host: str
    task_root: Path
    require_ai_station_nvme: bool


def _refuse(code: str, detail: str) -> RuntimeError:
    return RuntimeError(f"{code}: {detail}")


def load_registered_policy() -> GatePolicy:
    """Read and verify the operator-registered policy object frozen in this shell."""
    reference = os.environ.get(POLICY_REFERENCE_ENV, "").strip()
    expected_digest = os.environ.get(POLICY_DIGEST_ENV, "").strip()
    if not reference or not expected_digest:
        raise _refuse(
            "GATE_POLICY_UNREGISTERED",
            f"{POLICY_REFERENCE_ENV} and {POLICY_DIGEST_ENV} must both be set by the dispatcher",
        )
    path = Path(reference)
    if not path.is_file():
        raise _refuse("GATE_POLICY_MISSING", f"{path} is not a readable policy object")
    raw = path.read_bytes()
    actual_digest = hashlib.sha256(raw).hexdigest()
    if actual_digest != expected_digest:
        raise _refuse(
            "GATE_POLICY_HASH_MISMATCH",
            f"registered {expected_digest} but {path} hashes to {actual_digest}",
        )
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _refuse("GATE_POLICY_INVALID", f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise _refuse("GATE_POLICY_INVALID", f"{path} must contain a JSON object")
    types = {"execution_host": str, "task_root": str, "require_ai_station_nvme": bool}
    for field, field_type in types.items():
        value = document.get(field)
        if field not in document or not isinstance(value, field_type):
            raise _refuse("GATE_POLICY_INVALID", f"{field} is missing or not {field_type.__name__}")
        if field_type is str and not value.strip():
            raise _refuse("GATE_POLICY_INVALID", f"{field} must not be empty")
    host = socket.gethostname()
    if document["execution_host"] != host:
        raise _refuse(
            "REGISTERED_HOST_MISMATCH",
            f"policy registers {document['execution_host']} but this host is {host}",
        )
    return GatePolicy(
        execution_host=document["execution_host"],
        task_root=Path(document["task_root"]),
        require_ai_station_nvme=document["require_ai_station_nvme"],
    )


def run_gate(*, root: Path, python: Path, argv: list[str], policy: GatePolicy) -> int:
    """Run ``argv`` under a proven interpreter/scratch pair and retain the record.

    Returns the child exit code. Raises before spawning the command when the root or the
    interpreter/scratch proof does not match the registered policy.
    """
    root = Path(root).resolve(strict=True)
    registered_root = Path(policy.task_root).resolve(strict=True)
    if root != registered_root:
        raise _refuse("REGISTERED_ROOT_MISMATCH", f"{root} is not the registered {registered_root}")
    if policy.require_ai_station_nvme and not root.is_relative_to(NVME_EVIDENCE_ROOT):
        raise _refuse(
            "REGISTERED_NVME_ROOT_REQUIRED",
            f"{root} must live under {NVME_EVIDENCE_ROOT} for this registered host",
        )
    python = Path(python)
    if not python.is_file():
        raise _refuse("TEST_PYTHON_MISSING", f"{python} is not a file")
    run_dir = root / "gates" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    scratch = run_dir / "tmp"
    scratch.mkdir()
    environment = dict(os.environ, TMPDIR=str(scratch), TMP=str(scratch), TEMP=str(scratch))
    proof = subprocess.check_output(
        [str(python), "-c", PROOF_PROGRAM], env=environment, text=True
    ).splitlines()
    if (
        len(proof) < 2
        or Path(proof[0]).resolve() != python.resolve()
        or Path(proof[1]).resolve() != scratch.resolve()
    ):
        raise _refuse(
            "TEST_PYTHON_TEMP_MISMATCH",
            f"expected {python.resolve()} in {scratch.resolve()}, proof reported {proof!r}",
        )
    started = time.monotonic()
    with (run_dir / "stdout.txt").open("xb") as stdout, (run_dir / "stderr.txt").open("xb") as stderr:
        exit_code = subprocess.run(argv, env=environment, stdout=stdout, stderr=stderr, check=False).returncode
    elapsed = time.monotonic() - started
    (run_dir / "result.json").write_text(
        json.dumps(
            {
                "argv": [str(item) for item in argv],
                "test_python": proof[0],
                "tempfile_dir": proof[1],
                "exit_code": exit_code,
                "elapsed_seconds": elapsed,
                "registered_root": str(root),
                "execution_host": policy.execution_host,
                "require_ai_station_nvme": policy.require_ai_station_nvme,
                "policy_sha256": os.environ.get(POLICY_DIGEST_ENV, ""),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if not argv:
        parser.error("command required after --")
    policy = load_registered_policy()
    raise SystemExit(run_gate(root=args.root, python=args.python, argv=argv, policy=policy))


if __name__ == "__main__":
    main()
