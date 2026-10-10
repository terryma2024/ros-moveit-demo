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

# schema 2: the frozen contract plus the optimisation hyper-parameters and the normalisation std floor
_CONFIG_KEYS = frozenset({"schema_version", "kind", "action", "observation", "normalization", "frozen", "training"})
_TRAINING_KEYS = frozenset({"steps", "learning_rate", "batch_size", "pretrained_backbone"})
_ACTION_KEYS = frozenset({"chunk_size", "execution_prefix", "temporal_ensembling", "tail_padding_mask"})
_OBSERVATION_KEYS = frozenset({"cameras", "state_dim", "action_dim"})
_FROZEN_KEYS = frozenset({"seed", "preprocessing_sha256"})
_CAMERAS = ("head", "wrist")
CAMERAS = _CAMERAS
STATE_DIM = 8
ACTION_DIM = 6
_SMOKE_CHUNK_SIZE = 10
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
    if type(action["chunk_size"]) is not int or action["chunk_size"] != _SMOKE_CHUNK_SIZE:
        # the candidate chunk is frozen: a different value is a new contract, not an edit
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
    if tuple(observation["cameras"]) != _CAMERAS:
        raise ValueError("TRAINING_CAMERAS_INVALID")
    if observation["state_dim"] != STATE_DIM or observation["action_dim"] != ACTION_DIM:
        # the plan's contract is two RGB views and an 8-dimensional state to a 6-joint action block
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
    if not isinstance(training, dict) or set(training) != _TRAINING_KEYS:
        raise ValueError("TRAINING_CONFIG_INVALID")
    if type(training["steps"]) is not int or training["steps"] < 1:
        raise ValueError("TRAINING_STEPS_INVALID")
    if type(training["batch_size"]) is not int or training["batch_size"] < 1:
        raise ValueError("TRAINING_BATCH_SIZE_INVALID")
    if not _positive_float(training["learning_rate"]):
        raise ValueError("TRAINING_LEARNING_RATE_INVALID")
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
