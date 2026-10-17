from pathlib import Path
import os
import pytest
from archive_fixture import ArchiveFixture

@pytest.fixture
def archive(tmp_path):
    assert tmp_path.resolve().is_relative_to(Path(os.environ['TMPDIR']).resolve())
    return ArchiveFixture(tmp_path)
