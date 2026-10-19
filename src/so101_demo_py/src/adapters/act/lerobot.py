"""The LeRobot-backed adapter: the loader `load_policy` injects and the trainer `train_act` injects.

Two boundaries live here. The loader resolves the policy **inside the bundle**, refuses a hash mismatch, and
exposes exactly what the runner requires: `infer(observation)` returning an action chunk as tuples of floats,
and `reset()`. The observation it accepts is the runner's four-key mapping, converted to the LeRobot batch
layout (`observation.state`, `observation.images.head`, `observation.images.wrist`) on the policy's device.

The trainer (`train_act_bundle`) runs over a training view of an exported dataset: it decodes the frames through the single D8
table, computes train-only normalisation statistics (with a std floor), trains a LeRobot 0.6.1 `ACTPolicy` with AdamW and leaves a
bundle carrying the frozen action semantics and those statistics. LeRobot 0.6.1 keeps normalisation in separate processors, not in
the policy, so this adapter owns it: the statistics live in the bundle, the trainer normalises state and action with them, and
`LerobotPolicy.infer` normalises the state and de-normalises the action chunk with the same numbers. The policy is built with
`NormalizationMode.IDENTITY`; the pinned ImageNet ResNet18 backbone is loaded from a local, hash-verified file (never downloaded). Both the policy factory and the training
entry point are injectable so the wiring is testable without a GPU; the real LeRobot names used here were read from the resolved
interpreter (lerobot 0.6.1: `ACTPolicy`, `ACTConfig`, `predict_action_chunk`, `reset`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from so101_demo.act.rig_profile import DEFAULT_RIG, rig_from_frame_keys, rig_from_observation

_OBSERVATION_KEYS = frozenset({"sim_time_s", "state", *DEFAULT_RIG.camera_names})
#: the image keys of a policy without a declared camera set: the default rig's (v1); a bundle declares its own cameras
_IMAGE_KEYS = tuple((name, f"observation.images.{name}") for name in DEFAULT_RIG.camera_names)
_STATE_KEY = "observation.state"
_ACTION_KEYS = frozenset({"chunk_size", "execution_prefix", "temporal_ensembling", "tail_padding_mask"})
_POLICY_FILE = "policy.safetensors"
BUNDLE_FILE = "bundle.json"
_LOG_FILE = "training-log.json"
METRICS_FILE = "metrics.jsonl"
DEFAULT_LOG_INTERVAL_STEPS = 100
DEFAULT_VALIDATION_INTERVAL_STEPS = 2000
DEFAULT_VALIDATION_SAMPLES = 512
_MODEL_SOURCE = "lerobot-act"

#: D8: the one table that maps the recorder's PNG keys (sealed episodes and validators fix these names) to the runtime observation
#: keys. It is used by the dataset loader only; the runtime keys are the camera names of the rig. This is the table of the default
#: rig (v1: `head_png`->`head`, `wrist_png`->`wrist`); a rig's own table is `rig.decode_table` (`<camera>_png`->`<camera>`).
OBSERVATION_DECODE_TABLE = DEFAULT_RIG.decode_table

_IMAGE_PREPROCESSING = {"decode": "PNG -> uint8 HxWx3 RGB", "to_tensor": "float32 CHW, x / 255",
                        "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}


def preprocessing_for(rig) -> dict:
    """The frozen preprocessing of `rig`: its decode table, the image constants and the state and action widths. The hash of the
    default rig's (v1) document is the one the shipped training configs froze; another rig's table and width make another hash."""
    return {"observation_decode": dict(rig.decode_table), "image": _IMAGE_PREPROCESSING,
            "state_dim": rig.state_dim, "action_dim": 6}


#: Everything that turns a stored observation into a network input and is therefore frozen: the decode table, the image decode, the
#: image scaling and normalisation constants, and the state and action widths. `preprocessing_sha256()` is bound in the training config.
#: This is the default rig's (v1) document; `preprocessing_for(rig)` is any rig's.
PREPROCESSING = preprocessing_for(DEFAULT_RIG)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def preprocessing_sha256(rig=None) -> str:
    """The hash a training config freezes: of the default rig's (v1) preprocessing, or of `rig`'s."""
    return canonical_sha256(PREPROCESSING if rig is None else preprocessing_for(rig))


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


def _require_normalization(bundle: dict) -> dict:
    """The bundle's statistics, closed and finite: a bundle without them would leave normalisation to be guessed at run time."""

    import math

    normalization = bundle.get("normalization")
    keys = ("state_mean", "state_std", "action_mean", "action_std")
    if not isinstance(normalization, dict) or any(key not in normalization for key in keys):
        raise ValueError("BUNDLE_NORMALIZATION_STATS_MISSING")
    for key in keys:
        values = normalization[key]
        if (not isinstance(values, list) or not values
                or any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in values)):
            raise ValueError("BUNDLE_NORMALIZATION_INVALID")
    if (len(normalization["state_mean"]) != len(normalization["state_std"])
            or len(normalization["action_mean"]) != len(normalization["action_std"])
            or min(normalization["state_std"]) <= 0 or min(normalization["action_std"]) <= 0):
        raise ValueError("BUNDLE_NORMALIZATION_INVALID")
    return normalization


def _normalise_images(images):
    """uint8 NCHW tensor -> float32 NCHW, x / 255 then the frozen per-channel mean and std (training and inference share this)."""

    import torch

    mean = torch.tensor(PREPROCESSING["image"]["mean"], dtype=torch.float32, device=images.device).view(1, 3, 1, 1)
    std = torch.tensor(PREPROCESSING["image"]["std"], dtype=torch.float32, device=images.device).view(1, 3, 1, 1)
    return (images.to(torch.float32) / 255.0 - mean) / std


def _as_batch(observation: dict, device: str, normalization: dict | None = None, cameras=None) -> dict:
    import numpy as np                     # present in the training interpreter, imported at call time
    import torch

    image_keys = _IMAGE_KEYS if cameras is None else tuple((name, f"observation.images.{name}") for name in cameras)
    if (not isinstance(observation, dict)
            or set(observation) != {"sim_time_s", "state", *(key for key, _batch_key in image_keys)}):
        raise ValueError("OBSERVATION_INVALID")
    state = observation["state"]
    if not isinstance(state, (list, tuple)) or not state:
        raise ValueError("OBSERVATION_INVALID")
    values = np.asarray(list(map(float, state)), dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("OBSERVATION_INVALID")
    if normalization is not None:
        mean = np.asarray(normalization["state_mean"], dtype=np.float64)
        if values.shape != mean.shape:
            raise ValueError("OBSERVATION_INVALID")
        values = (values - mean) / np.asarray(normalization["state_std"], dtype=np.float64)
    batch = {_STATE_KEY: torch.tensor(values[None, :], dtype=torch.float32, device=device)}
    for key, batch_key in image_keys:
        array = np.asarray(observation[key])
        if array.ndim != 3 or array.shape[-1] != 3:
            raise ValueError("OBSERVATION_IMAGE_INVALID")
        if array.dtype != np.uint8:
            if not np.issubdtype(array.dtype, np.integer) or array.min() < 0 or array.max() > 255:
                raise ValueError("OBSERVATION_IMAGE_INVALID")
            array = array.astype(np.uint8)
        tensor = torch.from_numpy(np.ascontiguousarray(array)).to(device).permute(2, 0, 1).unsqueeze(0)
        batch[batch_key] = _normalise_images(tensor).contiguous()
    return batch


class LerobotPolicy:
    """The `infer`/`reset` interface the runner requires, over a LeRobot ACT policy.

    ``normalization`` is the bundle's statistics: the state is normalised before the network and the action chunk is
    de-normalised after it (LeRobot 0.6.1's policy does neither; its processors do, and the bundle does not use them)."""

    def __init__(self, policy: object, device: str = "cuda", normalization: dict | None = None,
                 cameras=None) -> None:
        self._policy = policy
        self._device = device
        self._normalization = normalization
        self._cameras = None if cameras is None else tuple(cameras)       # None = the shipped head and wrist

    def infer(self, observation: dict) -> tuple:
        import numpy as np

        batch = _as_batch(observation, self._device, self._normalization, self._cameras)
        chunk = self._policy.predict_action_chunk(batch)
        if hasattr(chunk, "detach"):
            chunk = chunk.detach().cpu().numpy()
        actions = np.asarray(chunk, dtype=np.float64)
        if actions.ndim == 3 and actions.shape[0] == 1:
            actions = actions[0]
        if actions.ndim != 2 or actions.shape[0] < 1:
            raise ValueError("POLICY_ACTION_INVALID")
        if self._normalization is not None:
            mean = np.asarray(self._normalization["action_mean"], dtype=np.float64)
            if actions.shape[1] != mean.shape[0]:
                raise ValueError("POLICY_ACTION_INVALID")
            actions = actions * np.asarray(self._normalization["action_std"], dtype=np.float64) + mean
        if not np.isfinite(actions).all():
            raise ValueError("POLICY_ACTION_INVALID")
        return tuple(tuple(float(value) for value in row) for row in actions)

    def reset(self) -> None:
        self._policy.reset()


def _act_config(chunk_size: int, execution_prefix: int, image_shape, device: str, learning_rate: float | None = None,
                head_learning_rate: float | None = None, cameras=None, state_dim: int | None = None):
    """The LeRobot 0.6.1 `ACTConfig` for this task: cameras head and wrist, state 8, action 6, no temporal ensembling.

    Normalisation is IDENTITY in the policy (the adapter normalises, see the module docstring) and the backbone has no pretrained
    weights, so building a policy never touches the network."""

    from lerobot.configs import FeatureType, NormalizationMode, PolicyFeature
    from lerobot.policies.act.configuration_act import ACTConfig

    from so101_demo.act.training_config import ACTION_DIM, CAMERAS, STATE_DIM

    if (not isinstance(image_shape, (list, tuple)) or len(image_shape) != 3 or image_shape[0] != 3
            or any(type(item) is not int or item < 1 for item in image_shape)):
        raise ValueError("BUNDLE_NORMALIZATION_INVALID")
    inputs = {_STATE_KEY: PolicyFeature(FeatureType.STATE, (STATE_DIM if state_dim is None else state_dim,))}
    for camera in (CAMERAS if cameras is None else cameras):
        inputs[f"observation.images.{camera}"] = PolicyFeature(FeatureType.VISUAL, tuple(image_shape))
    # head_learning_rate (the config key learning_rate_backbone) is the ACT backbone's rate; absent = the same as learning_rate
    extra = {} if learning_rate is None else {
        "optimizer_lr": learning_rate,
        "optimizer_lr_backbone": learning_rate if head_learning_rate is None else head_learning_rate}
    return ACTConfig(
        input_features=inputs, output_features={"action": PolicyFeature(FeatureType.ACTION, (ACTION_DIM,))},
        chunk_size=chunk_size, n_action_steps=execution_prefix, temporal_ensemble_coeff=None,
        pretrained_backbone_weights=None, device=device,
        normalization_mapping={"VISUAL": NormalizationMode.IDENTITY, "STATE": NormalizationMode.IDENTITY,
                               "ACTION": NormalizationMode.IDENTITY},
        **extra)


def _bundle_observation(bundle: dict) -> dict:
    """The cameras and state width of the bundle (its own declaration; the shipped head and wrist for an undeclared one)."""

    from so101_demo.act.policy import observation_spec
    from so101_demo.act.training_config import CAMERAS

    return observation_spec(bundle, legacy_cameras=CAMERAS)


def _load_act_policy(path: Path, bundle: dict, device: str) -> object:
    from lerobot.policies.act.modeling_act import ACTPolicy
    from safetensors.torch import load_model

    action = require_action_semantics(bundle.get("action"))
    spec = _bundle_observation(bundle)
    config = _act_config(action["chunk_size"], action["execution_prefix"],
                         _require_normalization(bundle).get("image_shape"), device,
                         cameras=spec["cameras"], state_dim=spec["state_dim"])
    policy = ACTPolicy(config)
    load_model(policy, str(path))                  # strict: every tensor of the saved policy must be present and fit
    return policy.to(device).eval()


def policy_loader(root: Path, *, factory=None, device: str = "cuda"):
    """Build the `loader` that `load_policy` injects: it resolves and verifies inside `root`.

    ``factory(path)`` builds the underlying policy from the verified weights file; the default rebuilds LeRobot's `ACTPolicy` from the
    bundle's own action semantics and image shape and loads the weights into it."""

    def loader(bundle: dict) -> LerobotPolicy:
        path = resolve_policy_file(root, bundle)
        normalization = _require_normalization(bundle)
        policy = factory(path) if factory is not None else _load_act_policy(path, bundle, device)
        declared = normalization.get("observation")
        cameras = declared["cameras"] if isinstance(declared, dict) and "cameras" in declared else None
        return LerobotPolicy(policy, device, normalization, cameras)

    return loader


def build_policy_from_bundle(root: Path, device: str = "cuda", *, bundle: dict | None = None, factory=None) -> LerobotPolicy:
    """The trained policy of the bundle at ``root`` (the directory holding `bundle.json` and `policy.safetensors`).

    The bundle document is re-read through `load_bundle` (closed schema, policy digest) unless the caller already holds the loaded
    document, and the weights file is hash-verified again by `policy_loader` before it is deserialised."""

    from so101_demo.act.bundle import load_bundle

    root = Path(root)
    if bundle is None:
        bundle = load_bundle(root / BUNDLE_FILE)
    return policy_loader(root, factory=factory, device=device)(bundle)


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
    extra = train(config or {"action": action, "dataset": str(dataset)}, Path(dataset), target)
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
        # whatever the train callable measured on the train split (statistics, floored dimensions, image shape) is the bundle's
        "normalization": {**(extra if isinstance(extra, dict) else {}), "split": "train",
                          "config_sha256": canonical_sha256(config or {"action": action})},
        "action": action,
    }
    return document



# ---- the dataset side: decode (D8), the training view, train-only statistics -------------------------------------------------------


def decode_png(path) -> "numpy.ndarray":
    """One stored frame -> uint8 HxWx3 RGB. Anything but an 8-bit RGB PNG is refused, never converted."""

    import numpy as np
    from PIL import Image

    try:
        with open(path, "rb") as stream:
            header = stream.read(26)
        if len(header) < 26 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[24] != 8 or header[25] != 2:
            raise ValueError("OBSERVATION_IMAGE_INVALID")           # not PNG, not 8 bit, or not colour type 2 (RGB)
        with Image.open(path) as image:
            if image.format != "PNG" or image.mode != "RGB":
                raise ValueError("OBSERVATION_IMAGE_INVALID")
            array = np.array(image, dtype=np.uint8)
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("OBSERVATION_IMAGE_INVALID") from error
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError("OBSERVATION_IMAGE_INVALID")
    return array


def decode_observation(observation: dict, dataset_root, rig=None) -> dict:
    """A stored observation -> the runtime observation: the D8 table maps each `<camera>_png` to the decoded `<camera>`.

    `rig` names the table; without it the rig is the one whose frame keys the stored observation carries (v1: `head_png` and
    `wrist_png` to `head` and `wrist`)."""

    root = Path(dataset_root)
    decoded = {"sim_time_s": observation["sim_time_s"], "state": list(observation["state"])}
    table = (rig_from_frame_keys(observation) if rig is None else rig).decode_table
    for png_key, key in table:
        relative = observation.get(png_key)
        if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
                or ".." in Path(relative).parts):
            raise ValueError("OBSERVATION_IMAGE_INVALID")           # a frame path never leaves the dataset
        decoded[key] = decode_png(root / relative)
    return decoded


def load_training_view(view) -> tuple:
    """(samples, dataset root) of a training view, with the dataset re-verified.

    The view holds no episodes and no frames: it names the exported dataset (`dataset_root`) and carries a byte copy of that dataset's
    export manifest. The manifest copy must still equal the dataset's, every episode and frame digest is re-verified, and the view's
    samples must equal what the whitelist reads from the dataset now."""

    from so101_demo.act.training import TRAINING_SAMPLES_FILE

    view = Path(view)
    try:
        document = json.loads((view / TRAINING_SAMPLES_FILE).read_bytes())
        view_manifest = (view / "export-manifest.json").read_bytes()
    except (OSError, ValueError) as error:
        raise ValueError("TRAINING_VIEW_INVALID") from error
    if (not isinstance(document, dict) or document.get("kind") != "act_training_samples"
            or not isinstance(document.get("dataset_root"), str) or not isinstance(document.get("samples"), list)):
        raise ValueError("TRAINING_VIEW_INVALID")
    root = Path(document["dataset_root"])
    try:
        dataset_manifest = (root / "export-manifest.json").read_bytes()
    except OSError as error:
        raise ValueError("TRAINING_VIEW_DATASET_MISMATCH") from error
    if dataset_manifest != view_manifest:
        raise ValueError("TRAINING_VIEW_DATASET_MISMATCH")
    samples, root = load_exported_samples(root)
    if document["samples"] != samples:
        raise ValueError("TRAINING_VIEW_SAMPLES_MISMATCH")
    return samples, root


def load_exported_samples(dataset_root) -> tuple:
    """(samples, resolved root) of an exported dataset: episode and frame digests re-verified, rows read through the whitelist.

    The one reader training (through a view) and offline evaluation share."""

    from so101_demo.act.training import load_training_samples, require_exported_dataset

    root = Path(dataset_root)
    manifest = require_exported_dataset(root)                    # episode and frame digests
    return load_training_samples(root, manifest=manifest), root.resolve()


def compute_statistics(samples: list, *, std_floor: float) -> dict:
    """Mean and std of state and action over the TRAIN split only; a std below ``std_floor`` is raised to it and the dimension recorded."""

    import numpy as np

    train = [sample for sample in samples if sample.get("split") == "train"]
    if not train:
        raise ValueError("TRAINING_NO_TRAIN_SPLIT")
    states = np.asarray([row["observation"]["state"] for sample in train for row in sample["rows"]], dtype=np.float64)
    actions = np.asarray([row["action"] for sample in train for row in sample["rows"]], dtype=np.float64)
    if states.ndim != 2 or actions.ndim != 2 or len(states) == 0:
        raise ValueError("TRAINING_NO_TRAIN_SPLIT")
    stats = {"split": "train", "std_floor": float(std_floor), "sample_count": int(len(states)), "episode_count": len(train),
             "floored_dims": {}}
    for name, values in (("state", states), ("action", actions)):
        std = values.std(axis=0)
        floored = std < std_floor
        stats[f"{name}_mean"] = [float(item) for item in values.mean(axis=0)]
        stats[f"{name}_std"] = [float(item) for item in np.where(floored, std_floor, std)]
        stats["floored_dims"][name] = [int(index) for index in np.flatnonzero(floored)]
    return stats


def first_motion_row(rows: list, threshold_rad: float) -> int | None:
    """The first row whose arm action differs from the arm state by more than ``threshold_rad`` on any of the six joints, in RAW units.

    State dimensions 0..5 are the arm joints (6 and 7 are the neck sin/cos); None when the episode never moves that much."""

    for index, row in enumerate(rows):
        state, action = row["observation"]["state"], row["action"]
        if any(abs(float(action[joint]) - float(state[joint])) > threshold_rad for joint in range(6)):
            return index
    return None


def _static_chunk_rows(rows: list, first: int, chunk_size: int, threshold_rad: float):
    """Per start row ``t >= first``: True when the whole next chunk is static, that is max over the chunk's actions ``a[t+k]`` (as many as
    the episode still has) and the six arm joints of ``|a[t+k] - s[t]|`` (RAW radians) is below ``threshold_rad``."""

    import numpy as np

    states = np.asarray([row["observation"]["state"][:6] for row in rows], dtype=np.float64)
    actions = np.asarray([row["action"][:6] for row in rows], dtype=np.float64)
    count = len(rows)
    deviation = np.zeros(count)
    for offset in range(chunk_size):
        usable = count - offset
        if usable > 0:
            deviation[:usable] = np.maximum(deviation[:usable], np.abs(actions[offset:] - states[:usable]).max(axis=1))
    return [bool(deviation[row] < threshold_rad) for row in range(first, count)]


def _episode_start_rows(rows: list, selection: dict | None, chunk_size: int | None) -> dict:
    """The selected start rows of one episode and how many each rule dropped.

    ``trim_leading_idle`` drops the rows before ``max(0, first_motion_row - lead_in_rows)``. ``trim_interior_idle`` then drops every row
    from there on whose next chunk is static, except the last ``keep_tail_rows`` rows of the episode. With ``trim_leading_idle`` an
    episode that never moves is kept whole."""

    moved, first = None, 0
    if selection and selection.get("trim_leading_idle"):
        moved = first_motion_row(rows, selection["idle_threshold_rad"])
        first = 0 if moved is None else max(0, moved - selection["lead_in_rows"])
    selected = list(range(first, len(rows)))
    interior = 0
    if selection and selection.get("trim_interior_idle") and (moved is not None or not selection.get("trim_leading_idle")):
        if chunk_size is None:
            raise ValueError("SAMPLE_SELECTION_CHUNK_SIZE_MISSING")
        tail_from = max(0, len(rows) - selection["keep_tail_rows"])
        static = _static_chunk_rows(rows, first, chunk_size, selection["idle_threshold_rad"])
        selected = [row for row, is_static in zip(range(first, len(rows)), static) if row >= tail_from or not is_static]
        interior = len(rows) - first - len(selected)
    return {"first_motion_row": moved, "first_start_row": first, "leading_trimmed": first, "interior_trimmed": interior, "rows": selected}


def sample_selection_report(samples: list, selection: dict | None, chunk_size: int | None = None) -> dict | None:
    """Per episode first-motion row, first sampled start row and (with ``trim_interior_idle``) the interior rows dropped; None when no
    selection rule is enabled."""

    if not selection or not (selection.get("trim_leading_idle") or selection.get("trim_interior_idle")):
        return None
    episodes = []
    for sample in samples:
        result = _episode_start_rows(sample["rows"], selection, chunk_size)
        entry = {"scene_id": sample.get("scene_id"), "rows": len(sample["rows"]), "first_motion_row": result["first_motion_row"],
                 "first_start_row": result["first_start_row"], "trimmed": result["leading_trimmed"]}
        if selection.get("trim_interior_idle"):
            entry["interior_trimmed"] = result["interior_trimmed"]
        episodes.append(entry)
    return {"episodes": episodes}


def _chunk_samples(samples: list, selection: dict | None = None, chunk_size: int | None = None) -> list:
    """Every (episode index, row index) of the given episodes: a chunk never starts in, or reaches into, another episode.

    With an enabled ``trim_leading_idle`` selection the start rows before ``max(0, first_motion_row - lead_in_rows)`` are dropped; with
    ``trim_interior_idle`` (which needs ``chunk_size``) the later start rows whose next chunk is static are dropped too, except the last
    ``keep_tail_rows``. The dropped rows stay available as action-window targets. An episode that never moves is kept whole."""

    if sample_selection_report([], selection) is None:
        return [(episode, row) for episode, sample in enumerate(samples) for row in range(len(sample["rows"]))]
    return [(episode, row) for episode, sample in enumerate(samples)
            for row in _episode_start_rows(sample["rows"], selection, chunk_size)["rows"]]


def selection_summary(samples: list, selection: dict | None, chunk_size: int | None = None) -> dict:
    """The selection settings and what they did to one split, for training-log.json and the metrics."""

    total = sum(len(sample["rows"]) for sample in samples)
    report = sample_selection_report(samples, selection, chunk_size)
    if report is None:
        return {"enabled": False, "samples_before": total, "samples_after": total}
    import statistics
    motion = [entry["first_motion_row"] for entry in report["episodes"] if entry["first_motion_row"] is not None]
    trimmed = sum(entry["trimmed"] for entry in report["episodes"])
    summary = {"enabled": True, "trim_leading_idle": bool(selection["trim_leading_idle"]), "idle_threshold_rad": selection["idle_threshold_rad"],
               "lead_in_rows": selection["lead_in_rows"], "episodes": len(samples), "never_moving_episodes": len(samples) - len(motion),
               "first_motion_row_min": min(motion) if motion else None,
               "first_motion_row_median": statistics.median(motion) if motion else None,
               "first_motion_row_max": max(motion) if motion else None,
               "samples_before": total, "samples_after": total - trimmed, "per_episode": report["episodes"]}
    if selection.get("trim_interior_idle"):
        interior = sum(entry["interior_trimmed"] for entry in report["episodes"])
        summary.update({"trim_interior_idle": True, "keep_tail_rows": selection["keep_tail_rows"], "leading_trimmed_rows": trimmed,
                        "interior_trimmed_rows": interior, "samples_after": total - trimmed - interior})
    return summary


def _action_window(actions, start: int, chunk_size: int) -> tuple:
    """(chunk x action_dim, pad mask) for the window at ``start``: the tail is padded with this episode's last action and masked."""

    import numpy as np

    window = actions[start:start + chunk_size]
    count = len(window)
    pad = np.zeros(chunk_size, dtype=bool)
    if count < chunk_size:
        pad[count:] = True
        window = np.concatenate([window, np.repeat(window[-1:], chunk_size - count, axis=0)], axis=0)
    return window.astype(np.float32), pad


# ---- the trainer ---------------------------------------------------------------------------------------------------------------------

_GRAD_CLIP_NORM = 10.0
_LOADER_TIMEOUT_S = 600     # a worker that died raises after this long instead of hanging the run
_WEIGHT_DECAY = 1e-4


def _config_rig(config: dict):
    """The rig a training config declares (`observation.cameras` and `state_dim`); a config without the declaration is the default rig."""
    observation = config.get("observation") if isinstance(config, dict) else None
    if not isinstance(observation, dict) or "cameras" not in observation:
        return DEFAULT_RIG
    try:
        return rig_from_observation(observation["cameras"], observation.get("state_dim"))
    except ValueError as error:
        raise ValueError("TRAINING_CONFIG_INVALID") from error


def _require_trainable_config(config: dict, requirements_sha256: str) -> None:
    if not isinstance(config, dict) or config.get("schema_version") != 2:
        raise ValueError("TRAINING_CONFIG_INVALID")
    if config.get("frozen", {}).get("preprocessing_sha256") != preprocessing_sha256(_config_rig(config)):
        # the config froze a different decode/normalisation than this adapter implements
        raise ValueError("TRAINING_PREPROCESSING_DRIFT")
    if not isinstance(requirements_sha256, str) or len(requirements_sha256) != 64:
        raise ValueError("TRAINING_REQUIREMENTS_SHA256_INVALID")


def _read_backbone_bytes(path, expected_sha256: str) -> bytes:
    """The pinned backbone file, read once and hash-verified."""

    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise ValueError("TRAINING_BACKBONE_MISSING") from error
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("TRAINING_BACKBONE_HASH_MISMATCH")
    return data


def _load_backbone(policy, path, expected_sha256: str) -> None:
    """Load the pinned ImageNet ResNet18 weights into the policy's backbone from local bytes (no download, no network).

    LeRobot would fetch `pretrained_backbone_weights` from the network; the adapter builds the policy without it and loads the
    verified file instead. The classifier head (`fc.*`) is not part of ACT's backbone and is dropped; everything else must fit."""

    import io

    import torch

    state = torch.load(io.BytesIO(_read_backbone_bytes(path, expected_sha256)), map_location="cpu", weights_only=True)
    policy.model.backbone.load_state_dict({key: value for key, value in state.items() if not key.startswith("fc.")}, strict=True)


def _prefetched(loader, depth: int = 2):
    """Yield the loader's batches from a background thread so a late DataLoader batch is absorbed by `depth` batches already waiting.

    Order and content are unchanged. The thread only waits on the worker queue (it releases the GIL), so the training step keeps its GPU
    queue full through the DataLoader's periodic multi-batch stalls (antzb profile: 11-13 % of the step time, 0 % with this)."""

    import queue
    import threading

    buffer: queue.Queue = queue.Queue(maxsize=depth)
    done = object()
    stop = threading.Event()

    def produce():
        try:
            for batch in loader:
                while not stop.is_set():
                    try:
                        buffer.put(batch, timeout=0.5)
                        break
                    except queue.Full:
                        continue
                if stop.is_set():
                    return
            item = done
        except BaseException as error:             # re-raised in the consumer, where the loader timeout error belongs
            item = error
        while not stop.is_set():
            try:
                buffer.put(item, timeout=0.5)
                return
            except queue.Full:
                continue

    thread = threading.Thread(target=produce, daemon=True)
    thread.start()
    try:
        while True:
            item = buffer.get()
            if item is done:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        stop.set()


def _run_training(config: dict, view: Path, target: Path, device: str, num_workers: int | None, backbone_weights=None) -> dict:
    """The LeRobot training loop; returns the normalisation block the bundle records."""

    import time

    import numpy as np
    import torch
    from lerobot.policies.act.modeling_act import ACTPolicy
    from safetensors.torch import save_model

    started = time.monotonic()
    if config["training"].get("cudnn_benchmark", False):
        torch.backends.cudnn.benchmark = True                           # opt-in: autotune the conv algorithms (not bit-identical)
    rig = _config_rig(config)
    cameras = rig.camera_names
    samples, root = load_training_view(view)
    stats = compute_statistics(samples, std_floor=config["normalization"]["std_floor"])
    train = [sample for sample in samples if sample["split"] == "train"]
    action_cfg, hyper = config["action"], config["training"]
    chunk_size = action_cfg["chunk_size"]
    state_mean, state_std = np.asarray(stats["state_mean"]), np.asarray(stats["state_std"])
    action_mean, action_std = np.asarray(stats["action_mean"]), np.asarray(stats["action_std"])
    def build_episodes(split_samples):
        built = []
        for sample in split_samples:
            rows = sample["rows"]
            states = ((np.asarray([row["observation"]["state"] for row in rows]) - state_mean) / state_std).astype(np.float32)
            actions = ((np.asarray([row["action"] for row in rows]) - action_mean) / action_std).astype(np.float32)
            built.append({"states": states, "actions": actions,
                          **{camera: [row["observation"][rig.frame_key(camera)] for row in rows] for camera in cameras}})
        return built

    episodes = build_episodes(train)
    first = decode_png(root / episodes[0][cameras[0]][0])
    image_shape = (3, int(first.shape[0]), int(first.shape[1]))

    selection = hyper.get("sample_selection")
    index = _chunk_samples(train, selection, chunk_size)
    selection_report = {"train": selection_summary(train, selection, chunk_size)}

    def chunks_dataset(episode_list, chunk_index):
        class _Chunks(torch.utils.data.Dataset):
            def __len__(self):
                return len(chunk_index)

            def __getitem__(self, position):
                episode_index, row = chunk_index[position]
                episode = episode_list[episode_index]
                images = {}
                for camera in cameras:
                    array = decode_png(root / episode[camera][row])
                    if array.shape != (image_shape[1], image_shape[2], 3):
                        raise ValueError("TRAINING_IMAGE_SHAPE_MISMATCH")
                    images[f"observation.images.{camera}"] = np.ascontiguousarray(array.transpose(2, 0, 1))
                chunk, pad = _action_window(episode["actions"], row, chunk_size)
                # numpy, not tensors: worker tensors travel through shared memory and a socket under TMPDIR, whose 107-byte path limit the
                # deep scratch directories of the evidence roots exceed (the DataLoader then hangs); pickled arrays need neither
                return {_STATE_KEY: episode["states"][row], **images, "action": chunk, "action_is_pad": pad}
        return _Chunks()

    def stack(items):
        return {key: np.stack([item[key] for item in items]) for key in items[0]}

    seed = config["frozen"]["seed"]
    torch.manual_seed(seed)
    generator = torch.Generator()
    generator.manual_seed(seed)
    if num_workers is not None:
        workers = num_workers                                   # an explicit argument wins
    elif "num_workers" in hyper:
        workers = hyper["num_workers"]                          # the training.yaml key (default 4)
    else:
        workers = 4 if str(device).startswith("cuda") else 0
    log_interval = hyper.get("log_interval_steps", DEFAULT_LOG_INTERVAL_STEPS)
    validation_interval = hyper.get("validation_interval_steps", DEFAULT_VALIDATION_INTERVAL_STEPS)
    validation_count = hyper.get("validation_samples", DEFAULT_VALIDATION_SAMPLES)
    loader = torch.utils.data.DataLoader(chunks_dataset(episodes, index), batch_size=hyper["batch_size"], shuffle=True, generator=generator,
                                         num_workers=workers, collate_fn=stack,
                                         persistent_workers=workers > 0, drop_last=False,
                                         timeout=_LOADER_TIMEOUT_S if workers > 0 else 0)
    policy = ACTPolicy(_act_config(chunk_size, action_cfg["execution_prefix"], image_shape, device,
                                   learning_rate=hyper["learning_rate"],
                                   head_learning_rate=hyper.get("learning_rate_backbone"),
                                   cameras=cameras, state_dim=rig.state_dim))
    backbone = hyper["pretrained_backbone"]
    if backbone is not None:
        _load_backbone(policy, backbone_weights, backbone["sha256"])
    policy.to(device).train()
    if hyper.get("channels_last", False):
        policy.model.backbone.to(memory_format=torch.channels_last)      # opt-in: no NCHW<->NHWC conversions; cuDNN picks other kernels (not bit-identical)
    if hyper.get("compile", False):
        policy.model.compile()          # opt-in torch.compile, in place: the state_dict keys (and so the saved weights) are unchanged
    optimizer = torch.optim.AdamW(policy.get_optim_params(), lr=hyper["learning_rate"], weight_decay=_WEIGHT_DECAY)

    # validation: the exported dataset's validation episodes (already digest-verified by load_training_view) over a fixed, evenly spaced
    # subset of their chunks. The loader owns its generator, so evaluating never advances the global or the training RNG.
    validation = [sample for sample in samples if sample["split"] == "validation"]
    validation_loader, validation_used = None, 0
    if validation:
        validation_index = _chunk_samples(validation, selection, chunk_size)
        selection_report["validation"] = selection_summary(validation, selection, chunk_size)
        picks = np.unique(np.linspace(0, len(validation_index) - 1, min(validation_count, len(validation_index))).astype(np.int64))
        validation_generator = torch.Generator()
        validation_generator.manual_seed(seed)
        validation_loader = torch.utils.data.DataLoader(
            chunks_dataset(build_episodes(validation), [validation_index[int(position)] for position in picks]),
            batch_size=hyper["batch_size"], shuffle=False, generator=validation_generator, num_workers=workers, collate_fn=stack,
            persistent_workers=False, drop_last=False, timeout=_LOADER_TIMEOUT_S if workers > 0 else 0)
        validation_used = int(len(picks))

    def to_device(batch):
        batch = {key: torch.from_numpy(value).to(device) for key, value in batch.items()}
        for camera in cameras:
            batch[f"observation.images.{camera}"] = _normalise_images(batch[f"observation.images.{camera}"])
        return batch

    metrics = open(Path(target) / METRICS_FILE, "w")

    def emit(entry, line):
        metrics.write(json.dumps(entry, sort_keys=True, allow_nan=False) + chr(10))
        metrics.flush()
        print(line, flush=True)

    if any(item["enabled"] for item in selection_report.values()):
        for split_name, item in selection_report.items():
            summary = {key: value for key, value in item.items() if key != "per_episode"}
            emit({"kind": "sample_selection", "split": split_name, **summary},
                 f"sample_selection {split_name} samples {item['samples_before']} -> {item['samples_after']} "
                 f"first_motion_row min/median/max={item.get('first_motion_row_min')}/{item.get('first_motion_row_median')}/"
                 f"{item.get('first_motion_row_max')} never_moving={item.get('never_moving_episodes')}"
                 + (f" leading_trimmed={item['leading_trimmed_rows']} interior_trimmed={item['interior_trimmed_rows']} "
                    f"keep_tail_rows={item['keep_tail_rows']}" if item.get("trim_interior_idle") else ""))

    def evaluate(at_step):
        """Mean loss over the fixed validation subset, in eval mode and without gradients; the training mode is restored."""
        began = time.monotonic()
        totals, count = {"loss": 0.0, "l1_loss": 0.0, "kld_loss": 0.0}, 0
        policy.eval()
        try:
            with torch.no_grad():
                for batch in validation_loader:
                    size = len(batch["action"])
                    loss, parts = policy(to_device(batch))
                    totals["loss"] += float(loss.item()) * size
                    totals["l1_loss"] += float(parts["l1_loss"]) * size
                    totals["kld_loss"] += float(parts.get("kld_loss", 0.0)) * size
                    count += size
        finally:
            policy.train()
        entry = {"kind": "validation", "step": at_step, "samples": count, "elapsed_s": time.monotonic() - began,
                 **{key: value / count for key, value in totals.items()}}
        if not all(np.isfinite(entry[key]) for key in totals):
            raise ValueError("TRAINING_VALIDATION_LOSS_NOT_FINITE")
        emit(entry, f"validation step={at_step} loss={entry['loss']:.5f} l1={entry['l1_loss']:.5f} samples={count}")
        return entry

    def fresh_window():
        return {"steps": 0, "samples": 0, "loss": 0.0, "l1_loss": 0.0, "kld_loss": 0.0, "wait_s": 0.0, "compute_s": 0.0}

    log, validations, step = [], [], 0
    window = fresh_window()
    previous_end = time.perf_counter()
    while step < hyper["steps"]:
        for batch in _prefetched(loader):
            # wait: the end of the previous optimiser step to the batch being on the host. compute: the batch to the end of the step,
            # which includes `loss.item()`; that already synchronises the device every step, so neither span needs an extra sync.
            batch_ready = time.perf_counter()
            batch = to_device(batch)
            loss, parts = policy(batch)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), _GRAD_CLIP_NORM)
            optimizer.step()
            step += 1
            value = float(loss.item())
            if not np.isfinite(value):
                raise ValueError("TRAINING_LOSS_NOT_FINITE")
            entry = {"step": step, "loss": value, "l1_loss": float(parts["l1_loss"]), "kld_loss": float(parts.get("kld_loss", 0.0))}
            log.append(entry)
            step_end = time.perf_counter()
            window["steps"] += 1
            window["samples"] += len(batch["action"])
            for key in ("loss", "l1_loss", "kld_loss"):
                window[key] += entry[key]
            window["wait_s"] += batch_ready - previous_end
            window["compute_s"] += step_end - batch_ready
            last = step >= hyper["steps"]
            if step % log_interval == 0 or last:
                n = window["steps"]
                busy = max(window["wait_s"] + window["compute_s"], 1e-9)
                record = {"kind": "train", "step": step, "loss": window["loss"] / n, "l1_loss": window["l1_loss"] / n,
                          "kld_loss": window["kld_loss"] / n, "learning_rate": float(optimizer.param_groups[0]["lr"]),
                          "samples_per_s": window["samples"] / busy, "elapsed_s": time.monotonic() - started,
                          "eta_s": (hyper["steps"] - step) * busy / n, "window_steps": n,
                          "wait_s_per_step": window["wait_s"] / n, "compute_s_per_step": window["compute_s"] / n,
                          "wait_share": window["wait_s"] / busy}
                emit(record, f"step={step}/{hyper['steps']} loss={record['loss']:.5f} l1={record['l1_loss']:.5f} "
                             f"kld={record['kld_loss']:.5f} lr={record['learning_rate']:.2e} {record['samples_per_s']:.1f} samples/s "
                             f"wait={record['wait_share']:.1%} elapsed={record['elapsed_s']:.0f}s eta={record['eta_s']:.0f}s")
                window = fresh_window()
            if validation_loader is not None and (step % validation_interval == 0 or last):
                validations.append(evaluate(step))
            previous_end = time.perf_counter()      # log and validation time is neither wait nor compute
            if last:
                break
    metrics.close()
    policy.eval()
    save_model(policy, str(Path(target) / _POLICY_FILE))
    last_validation = validations[-1] if validations else None
    (Path(target) / _LOG_FILE).write_text(json.dumps(
        {"schema_version": 1, "kind": "act_training_log", "device": str(device), "seed": seed, "steps_requested": hyper["steps"],
         "batch_size": hyper["batch_size"], "learning_rate": hyper["learning_rate"],
         "learning_rate_backbone": hyper.get("learning_rate_backbone", hyper["learning_rate"]),
         "sample_selection": selection_report, "train_samples": len(index),
         "elapsed_s": time.monotonic() - started, "steps": log,
         "metrics_file": METRICS_FILE, "num_workers": workers, "log_interval_steps": log_interval,
         "validation_interval_steps": validation_interval, "validation_samples": validation_used,
         "validations": validations, "last_validation": last_validation}, sort_keys=True, allow_nan=False) + chr(10))
    stats = {**stats, "last_validation": last_validation}
    # the bundle declares the cameras and state width it was trained with (read back by `policy.observation_spec`, the rollout
    # executor and the policy loader); a bundle written before this key existed is the default rig
    return {**stats, "image_shape": list(image_shape), "pretrained_backbone": backbone,
            "observation": {"cameras": list(cameras), "state_dim": rig.state_dim}}


def train_act_bundle(config: dict, dataset: Path, output: Path, *, requirements_sha256: str, device: str = "cuda",
                     num_workers: int | None = None, backbone_weights=None) -> dict:
    """Train an ACT policy over a training view and leave a bundle in ``output`` (design 2026-10-10 section 3.3).

    ``dataset`` is the training view `train_act` hands to a trainer. ``output`` receives `policy.safetensors`, `bundle.json` and
    `training-log.json`; the returned document is the bundle. ``backbone_weights`` is the local path of the pretrained backbone file
    the config pins by hash; it is verified here, before anything is written, and again when it is loaded."""

    _require_trainable_config(config, requirements_sha256)
    pinned = config["training"]["pretrained_backbone"]
    if pinned is None and backbone_weights is not None:
        raise ValueError("TRAINING_BACKBONE_NOT_CONFIGURED")
    if pinned is not None:
        if backbone_weights is None:
            raise ValueError("TRAINING_BACKBONE_PATH_REQUIRED")
        _read_backbone_bytes(backbone_weights, pinned["sha256"])

    def train(cfg, view, target):
        return _run_training(cfg, view, target, device, num_workers, backbone_weights)

    document = train_with_lerobot(config["action"], dataset, output, requirement_sha256=requirements_sha256, train=train, config=config)
    bundle_path = Path(output) / BUNDLE_FILE
    temporary = bundle_path.with_name(bundle_path.name + ".partial")
    import os
    with open(temporary, "w") as handle:
        handle.write(json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + chr(10))
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(bundle_path)
    from so101_demo.act.bundle import load_bundle
    return load_bundle(bundle_path)                                  # the closed document, the policy path and its digest
