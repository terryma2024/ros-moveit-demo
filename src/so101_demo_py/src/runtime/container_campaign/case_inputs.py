"""Host producer of one campaign's frozen inputs and per-scene collection scopes.

Everything it writes lives under `<run>/inputs`, a directory the mount rules accept as one read-only input (its first path
component is not a private Host directory). The frozen set is made by the real formal `freeze_inputs`, which keeps enforcing the
approval kinds, the `spot_check_candidate` refusal and the activation evidence root; nothing here creates or relaxes an
approval. The scene list is bound into `inputs_sha256`, so each row of it - and only a row of it - has a valid scope.
"""

import hashlib
from pathlib import Path

from so101_demo.act.collection_scope import build_collection_scope, write_collection_scope
from so101_demo.act.contact_policy import policy_fingerprint
from so101_demo.act.diagnostic_episode_inputs import (
    SCENE_MANIFEST_PATH, frozen_scene_rows, freeze_inputs, require_scope_for_inputs, verify_frozen_inputs)
from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.inference.config import validate_file_ref

INPUTS_DIRECTORY = 'inputs'
FROZEN_DIRECTORY = 'frozen'
SCOPES_DIRECTORY = 'scopes'
MANIFEST_NAME = 'inputs-manifest.json'
_HEX64 = '0123456789abcdef'
FORMAL_MODE = 'formal'
SPOT_CHECK_MODE = 'preselected_target_diagnostic'
#: plane -> (the frozen collection mode it needs, the refusal for another mode, the contact receipt kinds it accepts). The formal
#: and qualification planes collect real data: formal mode and a user activation only. The spot-check plane re-derives a contact
#: policy: diagnostic mode, and a plan-signed candidate receipt or a user activation (a harmless superset).
PLANES = {
    'formal': (FORMAL_MODE, 'CASE_INPUTS_NOT_FORMAL', ('user_activation',)),
    'qualification': (FORMAL_MODE, 'CASE_INPUTS_NOT_FORMAL', ('user_activation',)),
    'spot_check': (SPOT_CHECK_MODE, 'CASE_INPUTS_NOT_SPOT_CHECK', ('user_activation', 'spot_check_candidate')),
}


def _plane(plane):
    if plane not in PLANES:
        raise ValueError('CASE_INPUTS_PLANE_INVALID')
    return PLANES[plane]


def _ref(path):
    path = Path(path)
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _manifest_path(inputs_manifest):
    """The path of a manifest ref whose file still has the ref's hash; any other ref is one refusal."""
    try:
        return validate_file_ref(inputs_manifest)
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError('CASE_INPUTS_MANIFEST_REF_INVALID') from error


def _run_root(run):
    run = Path(run)
    if not run.is_absolute() or run.resolve(strict=True) != run or not run.is_dir():
        raise ValueError('CASE_INPUTS_RUN_INVALID')
    return run


def _sha(value, code):
    if type(value) is not str or len(value) != 64 or any(char not in _HEX64 for char in value):
        raise ValueError(code)
    return value


def freeze_campaign_inputs(run, *, candidates, scene_manifest, teacher_endpoint, teacher_execution_policy,
                           episode_recorder_policy, runtime_policy, rig_profile=None, plane='formal'):
    """Freeze the campaign's one formal input set into `<run>/inputs/frozen`; returns the ref of its manifest.

    `candidates` is the approved-candidate registry (`act_diagnostic_episode inspect`), `scene_manifest` the scene list to
    bind, and the four policy files the endpoint/execution/recorder policies and the development runtime whose `hard_stops`
    carry the disk floor. The freeze runs with the execution snapshot, formal mode and the scene list; an existing frozen
    directory is refused, never merged.

    `rig_profile` is the rig profile file (`config/act/rig-v*.yaml`) the campaign collects under; a campaign always freezes one.
    None names the default rig (v1), written explicitly from `act.rig_profile.DEFAULT_RIG`, so the manifest never has to be read
    as "no profile".

    `plane` names the campaign's plane (`PLANES`): `formal` and `qualification` freeze in formal mode; `spot_check` freezes in
    diagnostic mode, which admits a candidate receipt and a scene list of exactly one row.
    """
    from so101_demo.act.rig_profile import DEFAULT_RIG, dump_rig_profile

    mode = _plane(plane)[0]
    run = _run_root(run)
    target = run / INPUTS_DIRECTORY / FROZEN_DIRECTORY
    manifest = freeze_inputs(Path(candidates), target, mode=mode, execution_inputs=True,
                             scene_manifest=Path(scene_manifest), runtime_policy=Path(runtime_policy),
                             teacher_endpoint=Path(teacher_endpoint),
                             teacher_execution_policy=Path(teacher_execution_policy),
                             episode_recorder_policy=Path(episode_recorder_policy),
                             rig_profile=dump_rig_profile(DEFAULT_RIG) if rig_profile is None else Path(rig_profile))
    return _ref(manifest)


def _frozen(run, inputs_manifest):
    """The verified frozen set of `inputs_manifest`, which must be this run's own `inputs/frozen` manifest."""
    path = _manifest_path(inputs_manifest)
    if path != run / INPUTS_DIRECTORY / FROZEN_DIRECTORY / MANIFEST_NAME:
        raise ValueError('CASE_INPUTS_LOCATION_INVALID')
    return path, verify_frozen_inputs(path)


def write_case_scopes(run, *, inputs_manifest, plane='formal'):
    """Write one scope per row of the bound scene list under `<run>/inputs/scopes`; return the case-input mapping.

    The scope's mode is the frozen set's, which must be the plane's mode (`PLANES`).

    The mapping is `{scene_id: {'scope': ref, 'inputs_manifest': ref}}`, the shape the coordinator and the wave verifier
    require. An existing scopes directory is refused: scopes are written once, never overwritten or merged.
    """
    mode, mode_code, _ = _plane(plane)
    run = _run_root(run)
    path, frozen = _frozen(run, inputs_manifest)
    if frozen['mode'] != mode or 'scene_manifest' not in frozen:
        raise ValueError(mode_code)
    rows = frozen_scene_rows(frozen, path)
    directory = run / INPUTS_DIRECTORY / SCOPES_DIRECTORY
    try:
        directory.mkdir()
    except FileExistsError as error:
        raise ValueError('CASE_SCOPES_EXIST') from error
    cases = {}
    for row in rows:
        scope = build_collection_scope(mode, scene_id=row['scene_id'], seed=row['seed'],
                                       inputs_sha256=frozen['inputs_sha256'])
        require_scope_for_inputs(scope, frozen, path)
        target = directory / (row['scene_id'] + '.json')
        write_collection_scope(scope, target)
        cases[row['scene_id']] = dict(scope=_ref(target), inputs_manifest=dict(inputs_manifest))
    return cases


def campaign_binding(inputs_manifest, *, campaign_config, collection_config_sha256, scene_manifest_sha256, plane='formal'):
    """The values the campaign takes from the frozen set; refuses a set that is not this campaign's.

    `campaign_config` is the loaded campaign config. Refused: a manifest that is not its file's bytes, a set that is not formal
    or binds no scene list, another scene list, runtime or collection config than the campaign's, a contact proposal or
    receipt that is not an approved disabled proposal and, per `plane` (`PLANES`), a user activation of one policy (also a
    spot-check candidate receipt in the spot-check plane), a fingerprint that is not the proposal payload's, and a set without
    the runtime policy that carries the disk floor. The formal and qualification planes need a formal-mode set, the spot-check
    plane a diagnostic one.
    """
    mode, mode_code, receipts = _plane(plane)
    path = _manifest_path(inputs_manifest)
    _sha(collection_config_sha256, 'CASE_INPUTS_COLLECTION_CONFIG_MISMATCH')
    _sha(scene_manifest_sha256, 'CASE_INPUTS_SCENE_MANIFEST_MISMATCH')
    frozen = verify_frozen_inputs(path)
    if frozen['mode'] != mode:
        raise ValueError(mode_code)
    if 'scene_manifest' not in frozen:
        raise ValueError('CASE_INPUTS_SCENE_MANIFEST_UNBOUND')
    if frozen['scene_manifest']['sha256'] != scene_manifest_sha256:
        raise ValueError('CASE_INPUTS_SCENE_MANIFEST_MISMATCH')
    roles = frozen['roles']
    if roles['runtime_config']['sha256'] != campaign_config['controlled_runtime']['sha256']:
        raise ValueError('CASE_INPUTS_RUNTIME_CONFIG_MISMATCH')
    if roles['collection_config']['sha256'] != collection_config_sha256:
        raise ValueError('CASE_INPUTS_COLLECTION_CONFIG_MISMATCH')
    if (roles['contact_proposal']['approval'] != 'disabled_proposal'
            or roles['contact_activation']['approval'] not in receipts):
        raise ValueError('CASE_INPUTS_CONTACT_APPROVAL_INVALID')
    root = path.parent
    proposal = read_document(root / roles['contact_proposal']['path'])
    activation = read_document(root / roles['contact_activation']['path'])
    fingerprint = proposal.get('policy_fingerprint')
    if (type(proposal.get('payload')) is not dict or fingerprint != policy_fingerprint(proposal['payload'])
            or activation.get('policy_fingerprint') != fingerprint):
        raise ValueError('CASE_INPUTS_CONTACT_POLICY_MISMATCH')
    # the rig: the frozen set and the campaign config must name the same profile (a frozen set sealed before profiles existed, and a
    # campaign config that names none, are both rig v1), so data of different rigs never share one qualification or one campaign
    from so101_demo.act.rig_profile import DEFAULT_RIG, rig_from_frozen
    rig = rig_from_frozen(frozen)
    if rig.profile_sha256 != campaign_config.get('rig_profile_sha256', DEFAULT_RIG.profile_sha256):
        raise ValueError('CASE_INPUTS_RIG_PROFILE_MISMATCH')
    policy = frozen.get('runtime_policy')
    if type(policy) is not dict:
        raise ValueError('CASE_INPUTS_RUNTIME_POLICY_MISSING')
    floor = policy['hard_stops']['disk_free_min_bytes']
    if type(floor) is not int or floor <= 0:
        raise ValueError('CASE_INPUTS_DISK_FLOOR_INVALID')
    return dict(contact_policy_fingerprint=fingerprint, disk_floor_bytes=floor, rig_profile_sha256=rig.profile_sha256,
                scene_manifest=_ref(root / SCENE_MANIFEST_PATH))
