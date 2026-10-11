"""The episode scene preparation and the MuJoCo episode plant."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path

from so101_demo.act.head_search_deadband_measurement.plant import (
    MujocoClosedLoopPlant,
)
from so101_demo.act.head_search_fine_correction_episodes.contracts import (
    _BOUND_TOLERANCE_RAD,
    CAL_FINE_EPISODE_OUT_OF_CORRIDOR,
    CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
    DEFAULT_MEASUREMENT_BUDGET,
    _refuse,
)
from so101_demo.act.head_search_timing_measurement.contracts import (
    _finite,
)


def _resolve_config_scene(dataset_config_path) -> Path:
    """The MuJoCo scene a dataset profile renders, resolved from the profile's own declaration."""

    path = Path(dataset_config_path)
    if not path.is_file():
        raise FileNotFoundError(f"the fine-correction episodes need {path}")
    contents = path.read_text(encoding="utf-8")
    try:
        document = json.loads(contents)
    except json.JSONDecodeError:
        import yaml

        document = yaml.safe_load(contents)
    if not isinstance(document, Mapping) or "mjcf_path" not in document:
        raise _refuse(
            CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
            f"the dataset profile {path} declares no mjcf_path, so the scene these episodes would be "
            f"rendered from is not declared",
        )
    declared = Path(str(document["mjcf_path"]))
    return declared if declared.is_absolute() else (path.parent / declared).resolve()


def scene_preparation_request(
    *, dataset_config_path, generator_commit, seed, cup_count, scenario, scene_path, split
) -> dict:
    """The one request :func:`prepare_episode_scene` is called with, built in one place.

    The producer and the preparer have to agree on this mapping exactly - the preparer's signature is the
    contract - so it is built here rather than inline, and both are checked against each other by the
    tests. `scenario` and `split` are carried for the record: the scene a seed prepares depends on its cup
    count and its seed, and the condition class is the recorder's own name for that count.
    """

    return {
        "dataset_config_path": dataset_config_path,
        "generator_commit": generator_commit,
        "seed": int(seed),
        "cup_count": int(cup_count),
        "scenario": scenario,
        "scene_path": scene_path,
        "split": split,
    }


def prepare_episode_scene(
    *,
    dataset_config_path,
    generator_commit,
    seed,
    cup_count,
    scenario=None,
    scene_path=None,
    split=None,
) -> dict:
    """Prepare one held-out seed's scene exactly as the recorder prepared it, and snapshot it.

    The recorder (`record_episodes7.py`) built a `MuJoCoDatasetRenderer` from the head dataset profile and
    called `_prepare(numpy.random.default_rng(seed), DatasetScenario.for_cup_count(cups))` before it
    rendered a frame. This does the same and returns the state that preparation produced - the free joints,
    the camera position and the materials - so the plant can be put into that very scene rather than into
    a scene of its own.

    Every keyword :func:`scene_preparation_request` builds is accepted here, including the ones the scene
    does not depend on (`scenario`, `split`): the call has to be one call with one mapping, and a
    signature that silently dropped a key would prepare a scene nobody asked for.
    """

    import numpy as np

    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
        MuJoCoDatasetRenderer,
        load_dataset_config,
    )

    config = load_dataset_config(Path(dataset_config_path), generator_commit=generator_commit)
    renderer = MuJoCoDatasetRenderer(config)
    try:
        renderer._prepare(
            np.random.default_rng(int(seed)), DatasetScenario.for_cup_count(int(cup_count))
        )
        model, data = renderer._model, renderer._data
        state = {
            "qpos": [float(value) for value in data.qpos],
            "qvel": [float(value) for value in data.qvel],
            "cam_pos": [[float(value) for value in row] for row in model.cam_pos],
            "mat_rgba": [[float(value) for value in row] for row in model.mat_rgba],
            "scene_path": str(scene_path),
            "dataset_config_path": str(dataset_config_path),
            "generator_commit": str(generator_commit),
            "seed": int(seed),
            "cup_count": int(cup_count),
        }
    finally:
        renderer.close()
    return state


class MujocoEpisodePlant(MujocoClosedLoopPlant):
    """The sealed scene's neck, put into one held-out seed's prepared scene and commanded.

    This is the only place in this module that imports MuJoCo, and it does so through the deadband
    measurement's own plant, which commands the scene's ``neck_yaw_joint`` position actuator at the sealed
    controller period, applies the timing module's declared settle rule and renders the head camera. What
    this subclass adds is the prepared scene: the free joints, the camera position and the materials of the
    snapshot the dataset renderer produced are copied in, every *other* actuator is held at the position
    that preparation left it in (so the arm does not drift toward the actuators' unset targets while the
    neck moves), and the neck starts where the sealed anchor says.
    """

    def __init__(self, request: Mapping) -> None:
        super().__init__(request)
        self._start_rad = float(request["start_rad"])
        self._prepared_qpos = None
        self._arm_joints: list[int] = []
        self._prepared_cup_position_m = list(self.cup_position_m)
        self.apply_prepared_scene(request.get("scene_state"))

    def apply_prepared_scene(self, state) -> None:
        """Put this plant into the prepared scene, or leave the anchor's own placement standing."""

        if not isinstance(state, Mapping) or not state:
            return
        mujoco = self._mujoco
        qpos = [float(value) for value in state["qpos"]]
        if len(qpos) != self._model.nq:
            raise _refuse(
                CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
                f"the prepared scene carries {len(qpos)} positions and the sealed scene {self._model.nq}, "
                f"so these frames would be rendered from another model",
            )
        self._data.qpos[:] = qpos
        self._data.qvel[:] = 0.0
        # a scene may declare no material at all (`nmat` 0), so an empty snapshot is copied as nothing
        # rather than broadcast into a (0, 4) array; a non-empty one that does not fit is a refusal
        for name, values, count in (
            ("cam_pos", state["cam_pos"], int(self._model.ncam)),
            ("mat_rgba", state["mat_rgba"], int(self._model.nmat)),
        ):
            snapshot = [[float(value) for value in row] for row in values]
            if not snapshot and count == 0:
                continue
            if len(snapshot) != count:
                raise _refuse(
                    CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
                    f"the prepared scene carries {len(snapshot)} {name} rows and the sealed scene "
                    f"{count}, so these frames would be rendered from another model",
                )
            getattr(self._model, name)[:] = snapshot
        self._data.qpos[self._qpos_address] = float(self._start_rad)
        self._prepared_qpos = [float(value) for value in self._data.qpos]
        self._arm_joints = [
            int(self._model.actuator_trnid[actuator, 0])
            for actuator in range(self._model.nu)
            if int(self._model.actuator_trntype[actuator]) == int(mujoco.mjtTrn.mjTRN_JOINT)
            and int(self._model.actuator_trnid[actuator, 0]) != self._neck
        ]
        for actuator in range(self._model.nu):
            if int(self._model.actuator_trntype[actuator]) != int(mujoco.mjtTrn.mjTRN_JOINT):
                continue
            joint = int(self._model.actuator_trnid[actuator, 0])
            if joint == self._neck:
                continue
            value = float(self._data.qpos[int(self._model.jnt_qposadr[joint])])
            if bool(self._model.actuator_ctrllimited[actuator]):
                low, high = (float(bound) for bound in self._model.actuator_ctrlrange[actuator])
                value = min(max(value, low), high)
            self._data.ctrl[actuator] = value
        mujoco.mj_forward(self._model, self._data)
        # the capture has to follow `mj_forward`: `xpos` only holds the prepared scene once the model has
        # been forwarded with it, and a capture taken before that records the anchor placement instead
        self._prepared_cup_position_m = list(self.cup_position_m)

    @property
    def prepared_cup_position_m(self) -> list[float] | None:
        """Where the preparation left the cup, before the loop stepped the scene at all."""

        return None if self._prepared_cup_position_m is None else list(self._prepared_cup_position_m)

    @property
    def arm_drift_rad(self) -> float | None:
        """How far the held joints moved from the prepared scene, in radians (None before preparing)."""

        if self._prepared_qpos is None:
            return None
        return max(
            (
                abs(float(self._data.qpos[int(self._model.jnt_qposadr[joint])]) - self._prepared_qpos[
                    int(self._model.jnt_qposadr[joint])
                ])
                for joint in self._arm_joints
            ),
            default=0.0,
        )


def _measurement_budget(budget, *, start_rad: float, fine_corridor_rad) -> dict:
    """The declared instrument budget, checked against the interval a fine correction may travel in."""

    declared = dict(DEFAULT_MEASUREMENT_BUDGET if budget is None else budget)
    count = declared.get("max_fine_corrections")
    total = declared.get("max_fine_total_rad")
    if type(count) is not int or isinstance(count, bool) or count < 1:
        raise ValueError("the measurement budget needs a positive whole max_fine_corrections")
    if not _finite(total) or float(total) <= 0.0:
        raise ValueError("the measurement budget needs a positive finite max_fine_total_rad")
    low, high = (float(bound) for bound in fine_corridor_rad)
    if (
        start_rad - float(total) < low - _BOUND_TOLERANCE_RAD
        or start_rad + float(total) > high + _BOUND_TOLERANCE_RAD
    ):
        raise _refuse(
            CAL_FINE_EPISODE_OUT_OF_CORRIDOR,
            f"the declared measurement budget could command {float(total)} rad of fine correction from "
            f"the search start {start_rad}, which leaves the seal's lock-valid interval {[low, high]}",
        )
    return {"max_fine_corrections": int(count), "max_fine_total_rad": float(total)}


def scenario_name_for_cup_count(cup_count: int) -> str:
    """The dataset scenario name for a cup count, spelled as the renderer's own enum spells it."""

    from so101_demo.adapters.perception.mujoco_dataset import DatasetScenario

    return DatasetScenario.for_cup_count(int(cup_count)).value


def _cuda_available() -> bool:
    """Whether the declared CUDA device is really there; the measurement never falls back to the CPU."""

    import torch

    return bool(torch.cuda.is_available())
