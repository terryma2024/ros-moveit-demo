"""The LeRobot-backed adapter: the loader `load_policy` injects and the trainer `train_act` injects.

Two boundaries live here. The loader resolves the policy **inside the bundle**, refuses a hash mismatch, and
exposes exactly what the runner requires: `infer(observation)` returning an action chunk as tuples of floats,
and `reset()`. The observation it accepts is the runner's four-key mapping, converted to the LeRobot batch
layout (`observation.state`, `observation.images.head`, `observation.images.wrist`) on the policy's device.

The trainer runs LeRobot's own training entry point over an exported dataset and leaves a bundle carrying the
frozen action semantics and a train-only normalization. Both the policy factory and the training entry point
are injectable so the wiring is testable without a GPU, and neither is guessed at: the real LeRobot names used
here were read from the resolved interpreter (lerobot 0.6.1, `ACTPolicy`, `predict_action_chunk`, `reset`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_OBSERVATION_KEYS = frozenset({"sim_time_s", "state", "head", "wrist"})
_IMAGE_KEYS = (("head", "observation.images.head"), ("wrist", "observation.images.wrist"))
_STATE_KEY = "observation.state"
_ACTION_KEYS = frozenset({"chunk_size", "execution_prefix", "temporal_ensembling", "tail_padding_mask"})
_POLICY_FILE = "policy.safetensors"
_MODEL_SOURCE = "lerobot-act"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def require_action_semantics(action: object) -> dict:
    if not isinstance(action, dict) or set(action) != _ACTION_KEYS:
        raise ValueError("ACTION_SEMANTICS_INVALID")
    return action


def resolve_policy_file(root: Path, bundle: dict) -> Path:
    """The policy file must sit inside the bundle and match the bundle's own hash."""

    root = Path(root).resolve()
    relative = bundle.get("policy_path")
    if not isinstance(relative, str) or not relative:
        raise ValueError("POLICY_PATH_INVALID")
    candidate = (root / relative).resolve()
    if root not in candidate.parents and candidate.parent != root:
        raise ValueError("POLICY_PATH_ESCAPES_BUNDLE")
    if not candidate.is_file():
        raise ValueError("POLICY_FILE_MISSING")
    expected = bundle.get("policy_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("POLICY_SHA256_INVALID")
    if sha256_file(candidate) != expected:
        raise ValueError("POLICY_HASH_MISMATCH")
    return candidate


def _as_batch(observation: dict, device: str) -> dict:
    import numpy as np                     # present in the training interpreter, imported at call time
    import torch

    if not isinstance(observation, dict) or set(observation) != _OBSERVATION_KEYS:
        raise ValueError("OBSERVATION_INVALID")
    state = observation["state"]
    if not isinstance(state, (list, tuple)) or not state:
        raise ValueError("OBSERVATION_INVALID")
    batch = {_STATE_KEY: torch.tensor([list(map(float, state))], dtype=torch.float32, device=device)}
    for key, batch_key in _IMAGE_KEYS:
        image = observation[key]
        array = np.asarray(image)
        if array.ndim != 3 or array.shape[-1] != 3:
            raise ValueError("OBSERVATION_IMAGE_INVALID")
        tensor = torch.tensor(array, dtype=torch.float32, device=device) / 255.0
        batch[batch_key] = tensor.permute(2, 0, 1).unsqueeze(0).contiguous()
    return batch


class LerobotPolicy:
    """The `infer`/`reset` interface the runner requires, over a LeRobot ACT policy."""

    def __init__(self, policy: object, device: str = "cuda") -> None:
        self._policy = policy
        self._device = device

    def infer(self, observation: dict) -> tuple:
        batch = _as_batch(observation, self._device)
        chunk = self._policy.predict_action_chunk(batch)
        rows = chunk.tolist() if hasattr(chunk, "tolist") else chunk
        actions = []
        for row in rows:
            values = row[0] if row and isinstance(row[0], (list, tuple)) else row
            actions.append(tuple(float(value) for value in values))
        return tuple(actions)

    def reset(self) -> None:
        self._policy.reset()


def _default_factory(path: Path) -> object:
    from lerobot.policies.act.modeling_act import ACTPolicy

    return ACTPolicy.from_pretrained(str(path))


def policy_loader(root: Path, *, factory=None, device: str = "cuda"):
    """Build the `loader` that `load_policy` injects: it resolves and verifies inside `root`."""

    build = factory or _default_factory

    def loader(bundle: dict) -> LerobotPolicy:
        return LerobotPolicy(build(resolve_policy_file(root, bundle)), device)

    return loader


def _dataset_digest(dataset: Path) -> str:
    dataset = Path(dataset)
    manifest = dataset / "export-manifest.json"
    if manifest.is_file():
        return sha256_file(manifest)
    digest = hashlib.sha256()
    if dataset.is_dir():
        for path in sorted(item for item in dataset.rglob("*") if item.is_file()):
            digest.update(str(path.relative_to(dataset)).encode())
            digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def train_with_lerobot(action: dict, dataset: Path, target: Path, *, requirement_sha256: str,
                       train=None, config: dict | None = None) -> dict:
    """Run the injected LeRobot training entry point and return the bundle document it leaves."""

    require_action_semantics(action)
    if not callable(train):
        raise ValueError("LEROBOT_TRAIN_REQUIRED")
    action = dict(action)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    train(config or {"action": action, "dataset": str(dataset)}, Path(dataset), target)
    policy = target / _POLICY_FILE
    if not policy.is_file():
        raise ValueError("LEROBOT_POLICY_NOT_WRITTEN")
    document = {
        "schema_version": 1,
        "kind": "act_bundle",
        # the bundle validator requires model_source to be {name, sha256}: the requirements digest is the
        # provenance of the interpreter that produced the weights
        "model_source": {"name": _MODEL_SOURCE, "sha256": requirement_sha256},
        "dataset_sha256": _dataset_digest(dataset),
        "config_sha256": canonical_sha256(config or {"action": action}),
        "policy_path": _POLICY_FILE,
        "policy_sha256": sha256_file(policy),
        "normalization": {"split": "train", "config_sha256": canonical_sha256(config or {"action": action})},
        "action": action,
    }
    return document
