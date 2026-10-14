"""A controlled stand-in for `verify_container_task_registration`, importable in the readback worker processes.

The worker bootstrap is run through a wrapper interpreter that calls `install()` after the packages are registered. Behaviour per
scene comes from the `READBACK_DOUBLE` environment variable (a JSON object scene -> options), so the same function also serves
the in-process serial path. Options: `sleep` (seconds), `crash` (exit without a result), `hang`, `refuse` (raise ValueError),
`garbage` (a proof JSON cannot carry). `READBACK_DOUBLE_LOG` names a file that gets one line per finished scene.
`READBACK_DOUBLE_TREE` makes the worker lie about the code tree it runs (`worker-side`: its own check sees the mismatch;
`parent-side`: only the reply differs, which the parent must catch).
"""

import json
import os
from pathlib import Path
import time


def double(registration, *, scope, inputs_manifest, trust_independent_qc_memo=False):
    record = json.loads(Path(registration).read_text())
    scene = record['scene_id']
    options = json.loads(os.environ.get('READBACK_DOUBLE', '{}')).get(scene, {})
    time.sleep(options.get('sleep', 0))
    if os.environ.get('READBACK_DOUBLE_LOG'):
        with open(os.environ['READBACK_DOUBLE_LOG'], 'a') as stream:
            stream.write(scene + '\n')
    if options.get('crash'):
        os._exit(9)
    if options.get('hang'):
        time.sleep(3600)
    if options.get('refuse'):
        raise ValueError('REFUSED:' + scene)
    proof = dict(kind='ACT_CONTAINER_TASK_READBACK', schema_version=1, status='PASS', task_id=record['task_id'],
                 worker_id=record['worker_id'], scene_id=scene, location=record['host_output'], export_eligible=False,
                 scope=str(scope), inputs_manifest=str(inputs_manifest), ratio=0.1 + len(scene), nothing=None)
    if options.get('garbage'):
        proof['unrepresentable'] = {1, 2}
    return proof


def install():
    from so101_demo.act import result_store
    from so101_demo.runtime.container_campaign import readback_pool

    result_store.verify_container_task_registration = double
    mode = os.environ.get('READBACK_DOUBLE_TREE')
    if mode:
        real = readback_pool.import_identity_of

        def other_tree(identity):
            return {name: dict(where, file=where['file'] + '.other') for name, where in real(identity).items()}

        readback_pool.import_identity_of = other_tree
        if mode == 'parent-side':
            readback_pool.assert_same_code_tree = lambda identity: None
