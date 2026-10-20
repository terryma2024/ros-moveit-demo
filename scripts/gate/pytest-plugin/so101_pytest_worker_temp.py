"""Keep each pytest-xdist worker's fixtures inside its own registered NVMe scratch."""
import json
import os
from pathlib import Path
import tempfile


def pytest_configure(config):
    worker = os.environ.get('PYTEST_XDIST_WORKER')
    if not worker:
        return
    base = Path(os.environ['TMPDIR']).resolve()
    worker_root = base / worker
    worker_root.mkdir(mode=0o700, exist_ok=False)
    target = worker_root / 'tmp'
    target.mkdir(mode=0o700)
    for name in ('TMPDIR', 'TMP', 'TEMP'):
        os.environ[name] = str(target)
    tempfile.tempdir = None
    actual = Path(tempfile.gettempdir()).resolve()
    assert actual == target and actual.is_relative_to(base)
    (base.parent / f'worker-proof-{worker}.json').write_text(json.dumps({
        'worker': worker, 'python': os.sys.executable, 'tempdir': str(actual),
    }) + '\n')
