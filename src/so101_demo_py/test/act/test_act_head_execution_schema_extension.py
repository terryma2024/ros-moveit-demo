"""Directed tests for the CP-HFP-078/079 schema extension (PARKED, never executed).

Land with the sealed-input extension (binding + report + snapshot_root + the CP-HFP-075 run
declarations), the runner's switch to binding.search_config(...) and the provider's real detector
assembly. Written against the interfaces read in CP-HFP-076/077/079; the landing round must
dev-run and adapt it first, exactly as the parked runner test required.
"""

import hashlib
import importlib
import inspect
import json
from pathlib import Path

import pytest

from test_act_head_execution_documents import CONFIG, inputs_with_config


def documents_module():
    return importlib.import_module('so101_demo.act.head_execution_documents')


def inputs_module():
    return importlib.import_module('so101_demo.act.head_execution_inputs')


def binding_module():
    return importlib.import_module('so101_demo.act.head_search.binding')


NEW_REFS = ('binding', 'report')

DECLARATIONS = {
    'stop_declaration': {'trigger': 'OPERATOR_STOP', 'teardown_timeout_s': 1.},
    'seal_expectation': {'completion': True, 'artifacts': ['completion.json', 'seal.json']},
    'log_capture': {'stdout': 'pytest.stdout', 'stderr': 'pytest.stderr'},
    'fault_stop_probes': ['FAULT_PRIMARY'],
}


def declared_inputs(tmp_path, **changes):
    """inputs_with_config plus the four CP-HFP-075 declarations the closed schema now demands.

    The frozen helper predates the extension, so this wrapper writes the declarations into the
    document and re-parses it; when the helper itself learns them this wrapper becomes redundant.
    """

    import importlib
    inputs, policy = inputs_with_config(tmp_path, CONFIG)
    document = json.loads(inputs.document_path.read_text())
    root = Path(inputs.document_path).parent / 'extended-refs'
    root.mkdir(exist_ok=True)
    for name in NEW_REFS:
        payload = json.dumps({'name': name}).encode()
        path = root / ('%s.bin' % name)
        path.write_bytes(payload)
        document['refs'][name] = {'path': str(path),
                                  'sha256': hashlib.sha256(payload).hexdigest()}
    snapshot = root / 'snapshot'
    snapshot.mkdir(exist_ok=True)
    document['snapshot_root'] = str(snapshot)
    document.update({name: json.loads(json.dumps(value)) for name, value in DECLARATIONS.items()})
    inputs.document_path.write_text(json.dumps(document))
    module = importlib.import_module('so101_demo.act.head_execution_inputs')
    return module.HeadExecutionInputs.parse(inputs.document_path), policy


def test_the_closed_ref_set_names_the_binding_material():
    module = inputs_module()
    assert {'binding', 'report'} <= set(module.REF_NAMES), (
        'the sealed inputs must name the promoted binding material and its report as refs')
    assert 'snapshot_root' in module.TOP_LEVEL_FIELDS, (
        'the owned snapshot root is a declared directory field, never a sealed ref (CP-HFP-099)')


def test_the_closed_top_level_schema_names_the_run_declarations():
    module = inputs_module()
    assert {'stop_declaration', 'seal_expectation', 'log_capture',
            'fault_stop_probes'} <= set(module.TOP_LEVEL_FIELDS)


def test_the_stop_trigger_is_a_closed_set(tmp_path):
    module = inputs_module()
    inputs, policy = declared_inputs(tmp_path)
    document = json.loads(inputs.document_path.read_text())
    assert document['stop_declaration']['trigger'] == 'OPERATOR_STOP'
    document['stop_declaration'] = {'trigger': 'SOMETHING_ELSE', 'teardown_timeout_s': 1.}
    inputs.document_path.write_text(json.dumps(document))
    with pytest.raises(module.HeadExecutionInputsRefused):
        module.HeadExecutionInputs.parse(inputs.document_path)


def test_the_extension_reuses_the_existing_validator():
    module = binding_module()
    parameters = list(inspect.signature(module.validate_head_search_binding).parameters)
    assert parameters[:2] == ['runtime', 'calibration']
    assert callable(module.load_promoted_head_search)


def test_the_sealed_shape_check_still_works(tmp_path):
    inputs, policy = declared_inputs(tmp_path)
    documents = documents_module()
    assert documents.load_development_config(inputs)
    assert documents.sealed_bytes(inputs, 'local_policy')


def test_the_provider_detector_entry_names_the_real_builder():
    provider = importlib.import_module('so101_demo.adapters.act.head_execution_provider')
    assert provider.RESOURCE_MODULES['detector'][1] == 'build_bound_head_detector'
