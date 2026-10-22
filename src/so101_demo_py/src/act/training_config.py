"""The frozen training configuration.

The values that decide what a model was trained on — the action chunk, how much of it is executed, whether
temporal ensembling is used, the checkpoint seed and the preprocessing hash — are frozen here and refused
if they drift. The smoke configuration is deliberately conservative: it is a candidate, and changing it
requires the closed-loop validation and replay gate, not an edit.
"""

from __future__ import annotations

from pathlib import Path

import math

import yaml

from .rig_profile import DEFAULT_RIG, KNOWN_RIGS

# schema 2: the frozen contract plus the optimisation hyper-parameters and the normalisation std floor
_CONFIG_KEYS = frozenset({"schema_version", "kind", "action", "observation", "normalization", "frozen", "training"})
_TRAINING_KEYS = frozenset({"steps", "learning_rate", "batch_size", "pretrained_backbone"})
# optional keys, filled with these defaults when absent: progress logging, validation and the DataLoader width. None of them
# changes what is trained (the maths, the seed or the sampling order).
TRAINING_OPTIONAL_DEFAULTS = {"log_interval_steps": 100, "validation_interval_steps": 2000, "validation_samples": 512,
                              "num_workers": 4}
# optional keys that are NOT filled in when absent (an absent key keeps the config, and so its hash, as it was): the ACT backbone
# learning rate (absent = learning_rate) and the training-view sample selection (absent = every row starts a chunk)
_TRAINING_ABSENT_OK = frozenset({"learning_rate_backbone", "sample_selection", "compile", "cudnn_benchmark", "channels_last", "precision"})
SAMPLE_SELECTION_KEYS = frozenset({"trim_leading_idle", "idle_threshold_rad", "lead_in_rows"})
# optional selection keys, only together: drop the start rows whose whole next chunk is static, except the last keep_tail_rows rows
SAMPLE_SELECTION_INTERIOR_KEYS = frozenset({"trim_interior_idle", "keep_tail_rows"})
# alternative optional pair: remove the dwell rows from the episode timeline itself (observations and action targets), keep the last keep_tail_rows
SAMPLE_SELECTION_COMPRESS_KEYS = frozenset({"compress_dwell", "keep_tail_rows"})
_MAX_NUM_WORKERS = 64
#: Training keys that change only speed, logging or the validation cadence, never the trained policy (human, 2026-10-19: runtime
#: parameters are not hashed). `num_workers` must be at least 1: a non-persistent loader iterator (0 workers) takes an extra generator
#: draw per epoch and so changes the sampling order from epoch 2. The sampler and the model RNG live in the main process and
#: `__getitem__` is deterministic, so every value from 1 up gives the same batches.
RUNTIME_TRAINING_KEYS = frozenset({"num_workers", "log_interval_steps", "validation_interval_steps", "validation_samples"})
#: Values the trainer applies that no config key sets and that decide what is learned. They were hard-coded, and in no hash. They are
#: passed to the trainer explicitly (so an upstream default cannot change them silently) and hashed with the config.
OPTIMIZER_CONSTANTS = {"name": "AdamW", "weight_decay": 1e-4, "betas": [0.9, 0.999], "eps": 1e-8, "grad_clip_norm": 10.0}
ACT_MODEL_CONSTANTS = {"n_obs_steps": 1, "use_amp": False, "vision_backbone": "resnet18", "replace_final_stride_with_dilation": False,
                       "pre_norm": False, "dim_model": 512, "n_heads": 8, "dim_feedforward": 3200, "feedforward_activation": "relu",
                       "n_encoder_layers": 4, "n_decoder_layers": 1, "use_vae": True, "latent_dim": 32, "n_vae_encoder_layers": 4,
                       "dropout": 0.1, "kl_weight": 10.0}
#: 1 = the whole config dict, serialised two different ways by the lease and by the bundle; 2 = `config_sha256`
CONFIG_IDENTITY_VERSION = 2


def logic_config(config: dict) -> dict:
    """The part of a training config that decides the trained policy: the config without its runtime keys, with the constants the
    trainer applies and the identity version."""
    import copy

    logic = copy.deepcopy(config)
    training = logic.get("training")
    if isinstance(training, dict):
        for key in RUNTIME_TRAINING_KEYS:
            training.pop(key, None)
    logic["identity"] = {"config_identity_version": CONFIG_IDENTITY_VERSION, "optimizer": OPTIMIZER_CONSTANTS,
                         "act_model": ACT_MODEL_CONSTANTS}
    return logic


def config_sha256(config: dict) -> str:
    """The one `config_sha256` of a training run (lease, state and bundle): canonical JSON of `logic_config(config)`."""
    import hashlib
    import json

    return hashlib.sha256(json.dumps(logic_config(config), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()
_ACTION_KEYS = frozenset({"chunk_size", "execution_prefix", "temporal_ensembling", "tail_padding_mask"})
_OBSERVATION_KEYS = frozenset({"cameras", "state_dim", "action_dim"})
_FROZEN_KEYS = frozenset({"seed", "preprocessing_sha256"})
#: The default rig's (v1) cameras and state width; the config declares its own (a known rig's cameras with that rig's width).
CAMERAS = DEFAULT_RIG.camera_names
STATE_DIM = DEFAULT_RIG.state_dim
ACTION_DIM = 6
#: The chunk sizes a training config may declare (closed set; human 2026-10-22 added 50 for TRAIN-007). Anything else is a new contract.
ALLOWED_CHUNK_SIZES = (10, 50)
_SMOKE_EXECUTION_PREFIX = 1


def _positive_float(value) -> bool:
    return type(value) is float and math.isfinite(value) and value > 0.0


def load_training_config(path) -> dict:
    """Load the closed training config, refusing anything that would change what is trained."""

    target = Path(path)
    if not target.is_file():
        raise ValueError("TRAINING_CONFIG_MISSING")
    try:
        document = yaml.safe_load(target.read_bytes())
    except yaml.YAMLError as error:
        raise ValueError("TRAINING_CONFIG_INVALID") from error
    if not isinstance(document, dict) or type(document.get("schema_version")) is not int \
            or document["schema_version"] != 2:
        raise ValueError("TRAINING_CONFIG_INVALID")
    if set(document) != _CONFIG_KEYS or document["kind"] != "act_training":
        raise ValueError("TRAINING_CONFIG_INVALID")

    action = document["action"]
    if not isinstance(action, dict) or set(action) != _ACTION_KEYS:
        raise ValueError("TRAINING_CONFIG_INVALID")
    if type(action["chunk_size"]) is not int or action["chunk_size"] not in ALLOWED_CHUNK_SIZES:
        # the chunk is one of the allowed sizes: any other value is a new contract, not an edit
        raise ValueError("TRAINING_CHUNK_SIZE_DRIFT")
    if (type(action["execution_prefix"]) is not int
            or action["execution_prefix"] != _SMOKE_EXECUTION_PREFIX):
        raise ValueError("TRAINING_EXECUTION_PREFIX_DRIFT")
    if action["temporal_ensembling"] is not False:
        raise ValueError("TRAINING_TEMPORAL_ENSEMBLING_FORBIDDEN")
    if action["tail_padding_mask"] is not True:
        # a tail padded to complete a chunk must be masked, never completed with another episode's frames
        raise ValueError("TRAINING_PADDING_MASK_REQUIRED")

    observation = document["observation"]
    if not isinstance(observation, dict) or set(observation) != _OBSERVATION_KEYS:
        raise ValueError("TRAINING_CONFIG_INVALID")
    rigs = [rig for rig in KNOWN_RIGS.values() if rig.camera_names == tuple(observation["cameras"])]
    if not rigs:
        raise ValueError("TRAINING_CAMERAS_INVALID")
    if observation["state_dim"] != rigs[0].state_dim or observation["action_dim"] != ACTION_DIM:
        # the contract is the cameras of one known rig and that rig's state width (8 with the neck, 6 without), to a 6-joint action block
        raise ValueError("TRAINING_DIMENSIONS_INVALID")

    normalization = document["normalization"]
    if not isinstance(normalization, dict) or normalization.get("split") != "train":
        raise ValueError("TRAINING_NORMALIZATION_NOT_TRAIN_ONLY")
    if set(normalization) != {"split", "std_floor"}:
        raise ValueError("TRAINING_CONFIG_INVALID")
    if not _positive_float(normalization["std_floor"]):
        # a dimension with no spread (the neck under a fixed head) must still normalise to a finite value
        raise ValueError("TRAINING_STD_FLOOR_INVALID")
    training = document["training"]
    if not isinstance(training, dict) or not _TRAINING_KEYS <= set(training) <= _TRAINING_KEYS | set(TRAINING_OPTIONAL_DEFAULTS) | _TRAINING_ABSENT_OK:
        raise ValueError("TRAINING_CONFIG_INVALID")
    for key, default in TRAINING_OPTIONAL_DEFAULTS.items():
        training.setdefault(key, default)
    for key in ("log_interval_steps", "validation_interval_steps", "validation_samples"):
        if type(training[key]) is not int or training[key] < 1:
            raise ValueError(f"TRAINING_{key.upper()}_INVALID")
    if type(training["num_workers"]) is not int or not 1 <= training["num_workers"] <= _MAX_NUM_WORKERS:
        raise ValueError("TRAINING_NUM_WORKERS_INVALID")
    if type(training["steps"]) is not int or training["steps"] < 1:
        raise ValueError("TRAINING_STEPS_INVALID")
    if type(training["batch_size"]) is not int or training["batch_size"] < 1:
        raise ValueError("TRAINING_BATCH_SIZE_INVALID")
    if not _positive_float(training["learning_rate"]):
        raise ValueError("TRAINING_LEARNING_RATE_INVALID")
    if "learning_rate_backbone" in training and not _positive_float(training["learning_rate_backbone"]):
        raise ValueError("TRAINING_LEARNING_RATE_BACKBONE_INVALID")
    if "compile" in training and type(training["compile"]) is not bool:
        raise ValueError("TRAINING_COMPILE_INVALID")
    for key in ("cudnn_benchmark", "channels_last"):
        if key in training and type(training[key]) is not bool:
            raise ValueError(f"TRAINING_{key.upper()}_INVALID")

    if "precision" in training and training["precision"] not in ("fp32", "bf16"):
        raise ValueError("TRAINING_PRECISION_INVALID")
    if "sample_selection" in training:
        selection = training["sample_selection"]
        if (not isinstance(selection, dict) or not SAMPLE_SELECTION_KEYS <= set(selection)
                or set(selection) - SAMPLE_SELECTION_KEYS not in (set(), set(SAMPLE_SELECTION_INTERIOR_KEYS),
                                                                   set(SAMPLE_SELECTION_COMPRESS_KEYS))
                or type(selection["trim_leading_idle"]) is not bool
                or not _positive_float(selection["idle_threshold_rad"])
                or type(selection["lead_in_rows"]) is not int or selection["lead_in_rows"] < 0
                or ("trim_interior_idle" in selection
                    and (type(selection["trim_interior_idle"]) is not bool
                         or type(selection["keep_tail_rows"]) is not int or selection["keep_tail_rows"] < 0))
                or ("compress_dwell" in selection
                    and (type(selection["compress_dwell"]) is not bool
                         or type(selection["keep_tail_rows"]) is not int or selection["keep_tail_rows"] < 0
                         or (selection["compress_dwell"] and selection["trim_leading_idle"])))):
            raise ValueError("TRAINING_SAMPLE_SELECTION_INVALID")
    backbone = training["pretrained_backbone"]
    if backbone is not None and (
            not isinstance(backbone, dict) or set(backbone) != {"name", "sha256"}
            or not isinstance(backbone["name"], str) or not backbone["name"]
            or not isinstance(backbone["sha256"], str) or len(backbone["sha256"]) != 64):
        # the weights are pinned by name and hash (null = a randomly initialised backbone); the file path is a run argument
        raise ValueError("TRAINING_BACKBONE_INVALID")

    frozen = document["frozen"]
    if not isinstance(frozen, dict) or set(frozen) != _FROZEN_KEYS:
        raise ValueError("TRAINING_CONFIG_INVALID")
    if type(frozen["seed"]) is not int:
        raise ValueError("TRAINING_CONFIG_INVALID")
    if (not isinstance(frozen["preprocessing_sha256"], str)
            or len(frozen["preprocessing_sha256"]) != 64):
        raise ValueError("TRAINING_CONFIG_INVALID")
    return document
