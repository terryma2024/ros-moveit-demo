"""Immutable relative path input for a later broker-owned path proof."""

import copy
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import time
from types import MappingProxyType
from typing import Mapping

from .contracts import finite, integer, sha256, validate_action_prefix, vector
from .execution import prefix_sha256, split_positions
from .joints import ARM_JOINTS
from .prefix_source import PrefixSourceReceipt, SOURCE_KEYS, SOURCE_KINDS


def _nanoseconds(value):
    return round(finite(value, nonnegative=True) * 1_000_000_000)


@dataclass(frozen=True)
class RelativePathRequest:
    session_id: str
    attempt_id: str
    sequence: int
    source_observation_time_s: float
    prefix_issued_wall_s: float
    source_prefix_sha256: str
    source_start_ns: int
    source_bridge_ns: int
    observation_offset_ns: int
    bridge_offset_ns: int
    target_offsets_ns: tuple[int, ...]
    positions: tuple[tuple[float, ...], ...]
    first_target_delay_s: float | None
    target_interval_s: float | None
    source_receipt: PrefixSourceReceipt | None = None

    @property
    def oldest_source_wall_s(self):
        if self.source_receipt is None:
            raise ValueError('PATH_SOURCE_RECEIPT_REQUIRED')
        return min(value for _, value in self.source_receipt.source_received_wall_s)

    def matches_source(self, prefix):
        """Check every retained source field before a proof gains authority."""
        try:
            checked = validate_action_prefix(prefix)
            start = self.source_start_ns
            bridge = self.source_bridge_ns
            if (type(start) is not int or type(bridge) is not int
                    or start < 0 or bridge < 0):
                return False
            observation = _nanoseconds(checked['observation_time_s'])
            targets = tuple(_nanoseconds(value)
                            for value in checked['target_times_s'])
            return (
                self.session_id == checked['session_id']
                and self.attempt_id == checked['attempt_id']
                and self.sequence == checked['sequence']
                and self.source_observation_time_s == checked['observation_time_s']
                and self.source_prefix_sha256 == prefix_sha256(checked)
                and self.positions == checked['positions']
                and self.first_target_delay_s == checked.get('first_target_delay_s')
                and self.target_interval_s == checked.get('target_interval_s')
                and self.observation_offset_ns == observation - start
                and self.bridge_offset_ns == bridge - start
                and self.target_offsets_ns == tuple(value - start
                                                    for value in targets)
                and bridge <= observation < start < targets[0]
                and finite(self.prefix_issued_wall_s, nonnegative=True)
                    == self.prefix_issued_wall_s
                and (self.source_receipt is None or (
                    self.source_receipt.prefix_sha256 == self.source_prefix_sha256
                    and self.source_receipt.sequence == self.sequence
                    and self.source_receipt.owner_ticket[3:] ==
                        (self.session_id, self.attempt_id)
                    and self.source_receipt.prefix_issued_wall_s ==
                        self.prefix_issued_wall_s))
            )
        except (KeyError, TypeError, ValueError):
            return False

    def require_prefix_freshness(self, *, now_wall_s, max_age_s, jitter_s):
        age = finite(now_wall_s, nonnegative=True) - self.prefix_issued_wall_s
        limit = finite(max_age_s)
        jitter = finite(jitter_s, nonnegative=True)
        if limit <= 0 or not 0 <= age or not age + jitter < limit:
            raise ValueError('PREFIX_SOURCE_STALE')

    def require_source_freshness(self, *, now_wall_s,
                                 max_observation_age_s, max_prefix_age_s,
                                 jitter_s):
        receipt = self.source_receipt
        if receipt is None:
            raise ValueError('PATH_SOURCE_RECEIPT_REQUIRED')
        now = finite(now_wall_s, nonnegative=True)
        observation_limit = finite(max_observation_age_s)
        prefix_limit = finite(max_prefix_age_s)
        jitter = finite(jitter_s, nonnegative=True)
        received = receipt.source_received_wall_s
        if (observation_limit <= 0 or prefix_limit <= 0
                or tuple(key for key, _ in received) != SOURCE_KEYS
                or any(finite(value, nonnegative=True) > receipt.prefix_issued_wall_s
                       for _, value in received)
                or not receipt.prefix_issued_wall_s <= now):
            raise ValueError('PATH_SOURCE_RECEIPT_INVALID')
        if not now - min(value for _, value in received) + jitter < observation_limit:
            raise ValueError('PREFIX_OBSERVATION_STALE')
        if not now - receipt.prefix_issued_wall_s + jitter < prefix_limit:
            raise ValueError('PREFIX_SOURCE_STALE')

    @classmethod
    def from_prefix(cls, prefix, *, bridge_time_s, start_time_s,
                    prefix_issued_wall_s):
        checked = validate_action_prefix(prefix)
        observation_ns = _nanoseconds(checked['observation_time_s'])
        bridge_ns = _nanoseconds(bridge_time_s)
        start_ns = _nanoseconds(start_time_s)
        targets_ns = tuple(_nanoseconds(value) for value in checked['target_times_s'])
        if not bridge_ns <= observation_ns < start_ns < targets_ns[0]:
            raise ValueError('PATH_TIME_AXIS_INVALID')
        return cls(
            session_id=checked['session_id'], attempt_id=checked['attempt_id'],
            sequence=checked['sequence'],
            source_observation_time_s=checked['observation_time_s'],
            prefix_issued_wall_s=finite(prefix_issued_wall_s, nonnegative=True),
            source_prefix_sha256=prefix_sha256(checked),
            source_start_ns=start_ns, source_bridge_ns=bridge_ns,
            observation_offset_ns=observation_ns - start_ns,
            bridge_offset_ns=bridge_ns - start_ns,
            target_offsets_ns=tuple(value - start_ns for value in targets_ns),
            positions=checked['positions'],
            first_target_delay_s=checked.get('first_target_delay_s'),
            target_interval_s=checked.get('target_interval_s'),
        )

    @classmethod
    def from_source_receipt(cls, prefix, *, receipt, bridge_time_s,
                            start_time_s):
        checked = validate_action_prefix(prefix)
        if (not isinstance(receipt, PrefixSourceReceipt)
                or receipt.source_kind not in SOURCE_KINDS
                or receipt.prefix_sha256 != prefix_sha256(checked)
                or receipt.sequence != checked['sequence']
                or not isinstance(receipt.owner_ticket, tuple)
                or len(receipt.owner_ticket) != 5
                or receipt.owner_ticket[2:] != (
                    'act', checked['session_id'], checked['attempt_id'])
                or tuple(key for key, _ in receipt.source_received_wall_s)
                   != SOURCE_KEYS
                or receipt.command_authority is not False):
            raise ValueError('PATH_SOURCE_RECEIPT_INVALID')
        try:
            sha256(receipt.source_artifact_sha256)
            sha256(receipt.contact_policy_fingerprint)
            sha256(receipt.observation_sha256)
            integer(receipt.reset_epoch, minimum=1)
            integer(receipt.physics_step, minimum=1)
            issue_time = finite(receipt.prefix_issued_wall_s, nonnegative=True)
            times = tuple(finite(value, nonnegative=True)
                          for _, value in receipt.source_received_wall_s)
            if issue_time < max(times):
                raise ValueError('source order')
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('PATH_SOURCE_RECEIPT_INVALID') from error
        request = cls.from_prefix(
            checked, bridge_time_s=bridge_time_s,
            start_time_s=start_time_s,
            prefix_issued_wall_s=issue_time,
        )
        return replace(request, source_receipt=receipt)

    def checker_inputs(self, snapshot):
        if (_nanoseconds(snapshot['controller_start_time_s']) != self.source_start_ns
                or _nanoseconds(snapshot['controller_bridge']['time_s']) != self.source_bridge_ns):
            raise ValueError('PATH_SOURCE_TIME_CHANGED')
        canonical_start_ns = max(1_000_000_000,
                                 1_000_000_000 - self.bridge_offset_ns)
        prefix = {
            'session_id': self.session_id, 'attempt_id': self.attempt_id,
            'sequence': self.sequence,
            'observation_time_s': (canonical_start_ns + self.observation_offset_ns)
                                  / 1_000_000_000,
            'target_times_s': tuple((canonical_start_ns + offset)
                                    / 1_000_000_000 for offset in self.target_offsets_ns),
            'positions': self.positions,
        }
        if self.first_target_delay_s is not None:
            prefix['first_target_delay_s'] = self.first_target_delay_s
        if self.target_interval_s is not None:
            prefix['target_interval_s'] = self.target_interval_s
        checked = validate_action_prefix(prefix)
        shifted = copy.deepcopy(snapshot)
        shifted['controller_start_time_s'] = canonical_start_ns / 1_000_000_000
        shifted['controller_bridge']['time_s'] = (
            canonical_start_ns + self.bridge_offset_ns) / 1_000_000_000
        if 'sim_time_s' in shifted:
            shifted['sim_time_s'] = (canonical_start_ns
                                     + _nanoseconds(shifted['sim_time_s'])
                                     - self.source_start_ns) / 1_000_000_000
        return checked, shifted

    def materialize(self, *, start_time_s, bridge_time_s):
        start_ns = _nanoseconds(start_time_s)
        bridge_ns = _nanoseconds(bridge_time_s)
        if bridge_ns - start_ns != self.bridge_offset_ns:
            raise ValueError('BRIDGE_INTERVAL_CHANGED')
        materialized = {
            'session_id': self.session_id, 'attempt_id': self.attempt_id,
            'sequence': self.sequence,
            'source_observation_time_s': self.source_observation_time_s,
            'source_prefix_sha256': self.source_prefix_sha256,
            'bridge_time_s': bridge_ns / 1_000_000_000,
            'start_time_s': start_ns / 1_000_000_000,
            'target_times_s': tuple((start_ns + offset) / 1_000_000_000
                                    for offset in self.target_offsets_ns),
            'positions': self.positions,
        }
        materialized['prefix_issued_wall_s'] = self.prefix_issued_wall_s
        if self.source_receipt is not None:
            materialized['source_received_wall_s'] = (
                self.source_receipt.source_received_wall_s)
        return materialized


def _canonical_bytes(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('PATH_PROOF_INPUT_INVALID') from error


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _state_bytes(snapshot, nq, nv):
    try:
        bridge = snapshot['controller_bridge']
        point = bridge['point']
        attachment = snapshot['cup_in_gripper_transform']
        if attachment is not None:
            attachment = tuple(vector(row, 4) for row in attachment)
            if len(attachment) != 4:
                raise ValueError('PATH_PROOF_ATTACHMENT_INVALID')
        state = {
            'model_sha256': sha256(snapshot['model_sha256']),
            'model_qpos': vector(snapshot['model_qpos'], nq),
            'model_qvel': vector(snapshot['model_qvel'], nv),
            'phase': snapshot['phase'],
            'holding_state': snapshot['holding_state'],
            'cup_in_gripper_transform': attachment,
            'controller_bridge_point': {
                'positions': vector(point['positions'], 6),
                'velocities': tuple(finite(v) for v in point['velocities']),
                'accelerations': tuple(finite(v) for v in point['accelerations']),
            },
            'controller_start_positions': vector(
                snapshot['controller_start_positions'], 6),
            'controller_start_velocities': vector(
                snapshot['controller_start_velocities'], 6),
        }
        if 'holding_proof_physics_step' in snapshot:
            state['holding_proof_physics_step'] = snapshot['holding_proof_physics_step']
        # The proof input hashes the whole supplied snapshot. Keep every
        # supplied physical/source field in the commit comparison too; only
        # absolute times are translated by the relative path contract.
        supplied = dict(snapshot)
        supplied.pop('sim_time_s', None)
        supplied.pop('controller_start_time_s', None)
        supplied['controller_bridge'] = dict(bridge)
        supplied['controller_bridge'].pop('time_s', None)
        state['supplied_snapshot_state'] = supplied
        return _canonical_bytes(state)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('PATH_PROOF_STATE_INVALID') from error


@dataclass(frozen=True)
class PathProof:
    status: str
    canonical_input_sha256: str
    prefix_sha256: str
    snapshot_sha256: str
    state_sha256: str
    model_sha256: str
    policy_fingerprint: str
    profile_sha256: str
    contact_scope_sha256: str
    checker_sha256: str
    owner_ticket: tuple
    relative_request: RelativePathRequest
    controller_start_positions: tuple[float, ...]
    controller_start_velocities: tuple[float, ...]
    generation: int
    reset_epoch: int
    sample_count: int
    first_violation: Mapping | None
    started_wall_s: float
    completed_wall_s: float
    proof_compute_latency_s: float
    nq: int
    nv: int
    _state_canonical: bytes

    def matches_state(self, snapshot):
        try:
            return _state_bytes(snapshot, self.nq, self.nv) == self._state_canonical
        except ValueError:
            return False


class PathProver:
    """Run the existing full checker once; the broker owns any returned proof."""

    def __init__(self, checker, *, monotonic=time.monotonic):
        self.checker = checker
        self.monotonic = monotonic

    def prove(self, request, snapshot, *, ticket, reset_epoch,
              policy_fingerprint, profile_sha256, contact_scope_sha256,
              checker_sha256, expected_samples):
        started = finite(self.monotonic(), nonnegative=True)
        if (not isinstance(request, RelativePathRequest)
                or not isinstance(ticket, tuple) or len(ticket) != 5
                or ticket[2:] != ('act', request.session_id, request.attempt_id)):
            raise ValueError('PATH_PROOF_OWNER_INVALID')
        generation = integer(ticket[0])
        epoch = integer(reset_epoch)
        expected = integer(expected_samples, minimum=2)
        policy = sha256(policy_fingerprint)
        profile = sha256(profile_sha256)
        contact = sha256(contact_scope_sha256)
        checker_hash = sha256(checker_sha256)
        model_hash = sha256(self.checker.model_sha256)
        receipt = request.source_receipt
        if receipt is not None:
            received = receipt.source_received_wall_s
            if (receipt.owner_ticket != ticket or receipt.reset_epoch != epoch
                    or receipt.contact_policy_fingerprint != policy
                    or receipt.prefix_sha256 != request.source_prefix_sha256
                    or receipt.sequence != request.sequence
                    or tuple(key for key, _ in received) != SOURCE_KEYS
                    or not max(value for _, value in received)
                        <= receipt.prefix_issued_wall_s <= started):
                raise ValueError('PATH_PROOF_SOURCE_INVALID')
        if snapshot['model_sha256'] != model_hash:
            raise ValueError('PATH_PROOF_MODEL_INVALID')
        nq, nv = self.checker.model.nq, self.checker.model.nv
        state = _state_bytes(snapshot, nq, nv)
        relative_prefix, relative_snapshot = request.checker_inputs(snapshot)
        snapshot_bytes = _canonical_bytes(snapshot)
        input_bytes = _canonical_bytes({
            'version': 1, 'source_prefix_sha256': request.source_prefix_sha256,
            'source_receipt': None if request.source_receipt is None
                else asdict(request.source_receipt),
            'relative_prefix': relative_prefix,
            'snapshot': snapshot,
            'ticket': ticket, 'reset_epoch': epoch,
            'model_sha256': model_hash, 'policy_fingerprint': policy,
            'profile_sha256': profile, 'contact_scope_sha256': contact,
            'checker_sha256': checker_hash, 'expected_samples': expected,
            'path_step_s': finite(self.checker.step),
            'path_clearance_m': finite(self.checker.clearance),
        })
        safe = self.checker.check_path(relative_prefix, relative_snapshot)
        completed = finite(self.monotonic(), nonnegative=True)
        details = copy.deepcopy(self.checker.last_check)
        if (completed < started or type(safe) is not bool
                or not isinstance(details, dict)
                or details.get('safe') is not safe):
            raise ValueError('PATH_PROOF_RESULT_INVALID')
        count = details.get('samples' if safe else 'processed_samples', 0)
        if type(count) is not int or (safe and count != expected):
            raise ValueError('PATH_PROOF_SAMPLE_COUNT_INVALID')
        return PathProof(
            status='SAFE' if safe else 'VIOLATION',
            canonical_input_sha256=_digest(input_bytes),
            prefix_sha256=request.source_prefix_sha256,
            snapshot_sha256=_digest(snapshot_bytes), state_sha256=_digest(state),
            model_sha256=model_hash, policy_fingerprint=policy,
            profile_sha256=profile, contact_scope_sha256=contact,
            checker_sha256=checker_hash, owner_ticket=ticket,
            relative_request=request,
            controller_start_positions=vector(
                snapshot['controller_start_positions'], 6),
            controller_start_velocities=vector(
                snapshot['controller_start_velocities'], 6),
            generation=generation,
            reset_epoch=epoch, sample_count=count,
            first_violation=None if safe else MappingProxyType(details),
            started_wall_s=started, completed_wall_s=completed,
            proof_compute_latency_s=completed - started,
            nq=nq, nv=nv, _state_canonical=state,
        )


def goal_pair_from_proof(proof, *, start_time_s, bridge_time_s,
                         reference_positions):
    """Build the exact broker-side pair from a proven relative path."""
    if (not isinstance(proof, PathProof) or proof.status != 'SAFE'
            or proof.relative_request.source_prefix_sha256 != proof.prefix_sha256):
        raise ValueError('PATH_PROOF_NOT_SAFE')
    reference = vector(reference_positions, 6)
    if reference != proof.controller_start_positions:
        raise ValueError('PATH_REFERENCE_CHANGED')
    materialized = proof.relative_request.materialize(
        start_time_s=start_time_s, bridge_time_s=bridge_time_s)
    start = materialized['start_time_s']
    offsets = (0.,) + tuple(
        value / 1_000_000_000 for value in proof.relative_request.target_offsets_ns)
    arm, gripper = split_positions((reference,) + materialized['positions'])
    return tuple(dict(
        joint_names=names, header_stamp_s=start,
        time_from_start_s=offsets, positions=rows,
        session_id=proof.relative_request.session_id,
        attempt_id=proof.relative_request.attempt_id,
        sequence=proof.relative_request.sequence,
        prefix_sha256=proof.prefix_sha256,
    ) for names, rows in ((ARM_JOINTS[:5], arm), (ARM_JOINTS[5:], gripper)))


def require_proven_goals(proof, goals, *, bridge_time_s,
                         reference_positions):
    """Compare every field prepared for both action servers."""
    try:
        if len(goals) != 2:
            raise ValueError('goal pair')
        expected = goal_pair_from_proof(
            proof, start_time_s=goals[0]['header_stamp_s'],
            bridge_time_s=bridge_time_s,
            reference_positions=reference_positions)
        if tuple(goals) != expected:
            raise ValueError('goal content')
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('PATH_GOALS_MISMATCH') from error
    return True


def require_commit_window(proof, *, state_received_wall_s, accepted_wall_s,
                          accepted_sim_s, start_sim_s, max_state_age_s,
                          observation_jitter_s,
                          start_jitter_s, first_target_jitter_s,
                          clock_error_s, clock_continuous,
                          max_prefix_age_s=None, max_observation_age_s=None):
    """Apply both strict freshness and simulation-time acceptance bounds."""
    try:
        if (not isinstance(proof, PathProof) or proof.status != 'SAFE'
                or clock_continuous is not True):
            raise ValueError('proof or clock')
        state_wall = finite(state_received_wall_s, nonnegative=True)
        accepted_wall = finite(accepted_wall_s, nonnegative=True)
        accepted_sim = finite(accepted_sim_s, nonnegative=True)
        start_sim = finite(start_sim_s, nonnegative=True)
        max_state = finite(max_state_age_s)
        observation_jitter = finite(observation_jitter_s, nonnegative=True)
        start_jitter = finite(start_jitter_s, nonnegative=True)
        first_jitter = finite(first_target_jitter_s, nonnegative=True)
        clock_error = finite(clock_error_s, nonnegative=True)
        request = proof.relative_request
        receipt = request.source_receipt
        if max_state <= 0 or not proof.started_wall_s <= proof.completed_wall_s \
                <= state_wall <= accepted_wall:
            raise ValueError('wall order')
        state_age = accepted_wall - state_wall
        if receipt is None:
            max_prefix = finite(max_prefix_age_s)
            if (max_prefix <= 0 or max_observation_age_s is not None
                    or not request.prefix_issued_wall_s <= proof.started_wall_s):
                raise ValueError('prefix clock')
            prefix_age = accepted_wall - request.prefix_issued_wall_s
            source_ages = dict(prefix_age_s=prefix_age)
            source_fresh = prefix_age + observation_jitter + clock_error < max_prefix
        else:
            max_observation = finite(max_observation_age_s)
            max_prefix = finite(max_prefix_age_s)
            received = receipt.source_received_wall_s
            if (max_observation <= 0
                    or max_prefix <= 0
                    or tuple(key for key, _ in received) != SOURCE_KEYS
                    or not max(value for _, value in received)
                        <= receipt.prefix_issued_wall_s <= proof.started_wall_s):
                raise ValueError('source clocks')
            observation_age = accepted_wall - min(value for _, value in received)
            prefix_age = accepted_wall - receipt.prefix_issued_wall_s
            source_ages = dict(observation_age_s=observation_age,
                               prefix_age_s=prefix_age)
            source_fresh = (observation_age + observation_jitter + clock_error
                            < max_observation
                            and prefix_age + observation_jitter + clock_error
                            < max_prefix)
        first_target = (start_sim +
                        proof.relative_request.target_offsets_ns[0]
                        / 1_000_000_000)
        if (not state_age + observation_jitter + clock_error < max_state
                or not source_fresh
                or not accepted_sim + start_jitter + clock_error < start_sim
                or not accepted_sim + first_jitter + clock_error < first_target):
            raise ValueError('deadline')
        return dict(**source_ages, state_age_s=state_age,
                    commit_latency_s=state_age, first_target_sim_s=first_target,
                    clock_error_s=clock_error)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('COMMIT_WINDOW_INVALID') from error
