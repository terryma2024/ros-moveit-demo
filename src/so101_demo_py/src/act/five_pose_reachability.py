"""The five-pose Teacher reachability filter, as the formal scene generation ran it.

A cup position is kept only when the Teacher's own ``task_reachability`` check (``--ik-backend native``) reports REACHABLE
for the true pose and for the pose shifted by +0.01 m / -0.01 m in x and in y (the perception margin).  This is the
logic of ``generate_w8_scenes_reach.py`` (Reach and draw_filtered): phase 1 checks the true poses, phase 2 the four
offsets of those whose true pose is REACHABLE; an offset of a failed true pose is NOT_EVALUATED; an UNKNOWN verdict is
retried once and then aborts, and is never counted as a rejection.

The planner itself is reached through an injected ``call(points_document) -> {point_id: (status, failure_code)}``.
``CommandReachabilityCall`` is the production one: it runs the ``task_reachability`` executable through a command prefix.
"""

from __future__ import annotations

import json
import queue
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from so101_demo.act.scene_list_format import CUP_Z_M, write_new_json

OFFSET_M = 0.01
ROLES = (("true", 0.0, 0.0), ("x+", OFFSET_M, 0.0), ("x-", -OFFSET_M, 0.0), ("y+", 0.0, OFFSET_M), ("y-", 0.0, -OFFSET_M))
DEFAULT_BATCH_POSES = 80
REACHABLE = "REACHABLE"
NOT_EVALUATED = "NOT_EVALUATED"

Pose = tuple[float, float]
Verdict = tuple[str, str | None]
ReachCall = Callable[[dict], Mapping[str, Verdict]]


class ReachabilityUnknownError(RuntimeError):
    """The planner could not answer (UNKNOWN or a missing report) twice in a row."""


class PoseNotEvaluatedError(LookupError):
    """``is_reachable`` was asked about a position whose five poses were not evaluated yet."""

    def __init__(self, x: float, y: float) -> None:
        super().__init__(f"POSE_NOT_EVALUATED: {x} {y}")
        self.x, self.y = x, y


def pose_key(x: float, y: float) -> Pose:
    return (round(x, 6) + 0.0, round(y, 6) + 0.0)


def offset_poses(x: float, y: float) -> list[tuple[str, Pose]]:
    return [(role, pose_key(x + dx, y + dy)) for role, dx, dy in ROLES]


@dataclass
class FivePoseReachability:
    """Cached five-pose verdicts.  ``evaluate`` asks the planner; ``is_reachable`` only reads the cache."""

    call: ReachCall
    cup_z_m: float = CUP_Z_M
    batch_poses: int = DEFAULT_BATCH_POSES
    #: Several planners (one per execution stack). The chunks of one ``_ask`` run at the same time, one chunk per planner at a
    #: time; ids, cache and ``pose_log`` are filled in chunk order, so the outcome is the one a single planner would give.
    pool: Sequence[ReachCall] | None = None
    pose_log: list[dict] = field(default_factory=list)
    _cache: dict[Pose, Verdict] = field(default_factory=dict)
    _calls: int = 0

    @property
    def calls(self) -> int:
        return self._calls

    def _ask(self, poses: list[Pose], label: str) -> None:
        todo = [pose for pose in dict.fromkeys(poses) if pose not in self._cache]
        chunks = []
        for start in range(0, len(todo), self.batch_poses):
            chunk = todo[start:start + self.batch_poses]
            first = len(self._cache) + start
            ids = {f"p{first + i:05d}": pose for i, pose in enumerate(chunk)}
            document = {
                "schema_version": 1,
                "points": [
                    {"id": pid, "label": "reach-filter", "cup_position_world_m": [pose[0], pose[1], self.cup_z_m]}
                    for pid, pose in ids.items()
                ],
            }
            chunks.append((ids, document))
        self._calls += len(chunks)
        for (ids, _document), verdicts in zip(chunks, self._answers([document for _ids, document in chunks])):
            if set(verdicts) != set(ids) or any(status == "UNKNOWN" for status, _ in verdicts.values()):
                raise ReachabilityUnknownError(f"REACH_CALL_UNKNOWN: {label}")
            for pid, pose in ids.items():
                self._cache[pose] = tuple(verdicts[pid])  # type: ignore[assignment]
                self.pose_log.append(
                    {"pose_id": pid, "x": pose[0], "y": pose[1], "status": verdicts[pid][0],
                     "first_failure_code": verdicts[pid][1], "label": label}
                )

    def _answers(self, documents: list[dict]) -> list[Mapping[str, Verdict]]:
        if not self.pool or len(documents) < 2:
            return [self.call(document) for document in documents]
        idle: queue.Queue[ReachCall] = queue.Queue()
        for member in self.pool:
            idle.put(member)

        def ask(document: dict) -> Mapping[str, Verdict]:
            member = idle.get()
            try:
                return member(document)
            finally:
                idle.put(member)

        with ThreadPoolExecutor(max_workers=len(self.pool)) as executor:
            futures = [executor.submit(ask, document) for document in documents]
            return [future.result() for future in futures]

    def evaluate_true(self, positions: Iterable[Pose]) -> None:
        """Evaluate only the true pose of every position (a pre-fetch; the offsets follow for the positions that are used)."""

        self._ask([pose_key(x, y) for x, y in positions], "true")

    def evaluate(self, positions: Iterable[Pose]) -> None:
        """Evaluate all five poses of every position (true poses first, offsets only for the survivors)."""

        positions = [pose_key(x, y) for x, y in positions]
        self._ask(positions, "true")
        survivors = [p for p in positions if self._cache[p][0] == REACHABLE]
        self._ask([pose for p in survivors for _role, pose in offset_poses(*p)[1:]], "offsets")

    def verdict(self, x: float, y: float) -> dict[str, Verdict]:
        """Per role verdict; offsets of a failed true pose are NOT_EVALUATED.  Raises if the position is unknown."""

        poses = offset_poses(x, y)
        true = self._cache.get(poses[0][1])
        if true is None:
            raise PoseNotEvaluatedError(x, y)
        if true[0] != REACHABLE:
            return {"true": true, **{role: (NOT_EVALUATED, None) for role, _ in poses[1:]}}
        result = {}
        for role, pose in poses:
            if pose not in self._cache:
                raise PoseNotEvaluatedError(x, y)
            result[role] = self._cache[pose]
        return result

    def is_reachable(self, x: float, y: float) -> bool:
        return all(status == REACHABLE for status, _ in self.verdict(x, y).values())

    def optimistic(self) -> tuple[Callable[[float, float], bool], set[Pose]]:
        """A ``reachable`` that answers from the cache and, for an unknown position, answers True and records it.

        The recorded positions are then ``evaluate``d and the computation is run again, until nothing new is recorded.
        """

        missing: set[Pose] = set()

        def reachable(x: float, y: float) -> bool:
            try:
                return self.is_reachable(x, y)
            except PoseNotEvaluatedError:
                missing.add(pose_key(x, y))
                return True

        return reachable, missing


@dataclass
class CommandReachabilityCall:
    """Run the ``task_reachability`` executable through ``command`` (a prefix) for one batch of poses.

    The prefix gets three arguments appended: the points file, the evidence file and the session id; it must run
    ``task_reachability --points <points> --policy <policy> --session-id <id> --evidence-file <evidence> --ik-backend native``
    where the native stack runs (for the formal lists: ``reach_call.zsh <out> <container>`` ``docker exec``-ing into the
    ``so101_mujoco_act_execution_stack`` container).  The exit code is read from ``<evidence>.rc`` when the prefix writes
    one, else from the process.  0 and 2 (REACHABLE / UNREACHABLE) are answers; anything else is UNKNOWN.
    """

    command: list[str]
    directory: Path
    session_prefix: str = "boundary"
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run
    _count: int = 0

    def __call__(self, document: dict) -> Mapping[str, Verdict]:
        for attempt in (1, 2):
            self._count += 1
            base = f"{self.session_prefix}-c{self._count:04d}-a{attempt}"
            points, evidence = (self.directory / f"{base}.points.json", self.directory / f"{base}.evidence.json")
            write_new_json(points, document)
            completed = self.run([*self.command, str(points), str(evidence), base], check=False)
            rc_file = evidence.with_name(evidence.name + ".rc")
            rc = int(rc_file.read_text()) if rc_file.exists() else completed.returncode
            try:
                reports = {r["point_id"]: r for r in json.loads(evidence.read_text()).get("reports", [])}
            except (OSError, ValueError):
                reports = {}
            wanted = {p["id"] for p in document["points"]}
            if rc in (0, 2) and set(reports) == wanted and all(r["status"] != "UNKNOWN" for r in reports.values()):
                return {pid: (r["status"], r["first_failure_code"]) for pid, r in reports.items()}
        raise ReachabilityUnknownError(f"REACH_CALL_UNKNOWN: {base}")
