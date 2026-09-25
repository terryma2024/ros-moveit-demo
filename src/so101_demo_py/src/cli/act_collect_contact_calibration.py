"""Collect a sealed deterministic ACT MuJoCo calibration cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from so101_demo.act.contact_calibration import _canonical, _read_cohort, _write_exclusive, seal_cohort
from so101_demo.act.contact_collector import (
    _MODEL_SHA256, _MOTION_SHA256, _MUJOCO_VERSION, _SCENE_SHA256,
    collect_offline_sample,
)

_REGIMES = (
    "no_contact", "bilateral_touch", "over_compression", "micro_lift_slip", "stable_hold"
)
_CONTROLS = ("table_only", "post_release", "left_only", "right_only")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main(arguments=None):
    parser = argparse.ArgumentParser(prog="act_collect_contact_calibration")
    parser.add_argument("--mode", choices=("offline", "live"), required=True)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--motion-policy", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--regime", choices=(*_REGIMES, *_CONTROLS))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--session-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--ros-domain-id", type=int)
    parser.add_argument("--gz-partition")
    parser.add_argument("--tmux-name")
    parser.add_argument("--install-base", type=Path)
    parser.add_argument("--venv-python", type=Path)
    parser.add_argument("--source-commit")
    options = parser.parse_args(arguments)
    if options.mode == "live":
        from so101_demo.act.contact_live_calibration import (
            build_live_sample, live_collector_sha256,
        )
        from so101_demo.act.contact_live_session import run_live_session
        required = ("plugin", "metadata", "run_root", "regime", "seed", "session_id",
                    "attempt_id", "ros_domain_id", "gz_partition", "tmux_name",
                    "install_base", "venv_python", "source_commit")
        if any(getattr(options, name) is None for name in required):
            raise ValueError("live collector has missing session parameters")
        if not options.output_root.is_dir() or not (options.output_root / "samples").is_dir():
            raise ValueError("live campaign root and samples directory must already exist")
        sample_id = f"live-{options.regime}-{options.seed:03d}"
        sample_path = options.output_root / "samples" / f"{sample_id}.json"
        if sample_path.exists():
            raise FileExistsError(sample_path)
        metadata = json.loads(options.metadata.read_bytes())
        if metadata.get("live_collector_sha256") != live_collector_sha256():
            raise ValueError("live collector metadata hash does not match source")
        run = run_live_session(
            options.run_root, scene_path=options.scene,
            motion_policy_path=options.motion_policy, plugin_path=options.plugin,
            regime=options.regime, seed=options.seed,
            session_id=options.session_id, attempt_id=options.attempt_id,
            domain_id=options.ros_domain_id, partition=options.gz_partition,
            tmux_name=options.tmux_name, install_base=options.install_base,
            venv_python=options.venv_python, source_commit=options.source_commit,
        )
        sample = build_live_sample(
            run, regime=options.regime, seed=options.seed,
            sample_id=sample_id, metadata=metadata)
        payload = _canonical(sample) + b"\n"
        _write_exclusive(sample_path, payload)
        print(json.dumps({"status": "SEALED_SAMPLE", "sample": str(sample_path),
                          "run": str(run), "sample_sha256": hashlib.sha256(payload).hexdigest()},
                         sort_keys=True))
        return 0
    root = options.output_root
    root.mkdir(mode=0o750)
    _fsync_directory(root.parent)
    samples_root = root / "samples"
    samples_root.mkdir(mode=0o750)
    _fsync_directory(root)
    config = {
        "schema_version": 1,
        "mujoco_version": _MUJOCO_VERSION,
        "model_sha256": _MODEL_SHA256,
        "scene_sha256": _SCENE_SHA256,
        "motion_policy_sha256": _MOTION_SHA256,
        "policy_id": "so101-act-contact-20260925",
        "allowed_other_contact_bodies": ["table"],
        "evaluation": {"maximum_observation_age_s": .1, "minimum_consecutive_samples": 5},
        "diagnostic_limits": {
            "maximum_force_n": 11.6,
            "maximum_displacement_m": .03,
            "maximum_ros_skew_s": .02,
            "maximum_receipt_age_s": .2,
        },
        "offline_seed_start": 0,
        "offline_count_per_regime": 20,
    }
    config_bytes = _canonical(config) + b"\n"
    _write_exclusive(root / "config.json", config_bytes)
    config_hash = hashlib.sha256(config_bytes).hexdigest()
    from so101_demo.act import contact_calibration, contact_collector
    metadata = {key: config[key] for key in (
        "mujoco_version", "model_sha256", "scene_sha256", "motion_policy_sha256",
        "policy_id", "allowed_other_contact_bodies", "evaluation", "diagnostic_limits",
    )}
    metadata.update({
        "collector_sha256": _sha(Path(contact_collector.__file__)),
        "analyzer_sha256": _sha(Path(contact_calibration.__file__)),
        "config_sha256": config_hash,
    })
    _write_exclusive(root / "metadata.json", _canonical(metadata) + b"\n")
    samples = []
    for regime in (*_REGIMES, *_CONTROLS):
        count = 20 if regime in _REGIMES else 1
        for seed in range(count):
            sample_id = f"offline-{regime}-{seed:03d}"
            sample = collect_offline_sample(
                options.scene, options.motion_policy, regime=regime,
                seed=seed, sample_id=sample_id, config_sha256=config_hash,
            )
            _write_exclusive(samples_root / f"{sample_id}.json", _canonical(sample) + b"\n")
            samples.append(sample)
    cohort = {"source": "offline", "samples": samples}
    manifest = seal_cohort(root / "sealed", cohort)
    if _canonical(_read_cohort(manifest, "offline")) != _canonical(cohort):
        raise ValueError("sealed offline cohort readback mismatch")
    print(json.dumps({"status": "SEALED", "manifest": str(manifest),
                      "sample_count": len(samples), "config_sha256": config_hash}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
