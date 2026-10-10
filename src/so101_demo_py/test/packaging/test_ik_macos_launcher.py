"""The fixed Mac launcher must retain an explicit IK selection after cleaning its environment."""

import os
import shutil
import subprocess
import sys

import pytest
from paths import REPOSITORY


@pytest.mark.skipif(sys.platform != "darwin", reason="fixed macOS launcher contract")
def test_clean_mac_launcher_preserves_selected_ik_backend(tmp_path):
    root = REPOSITORY
    scripts = tmp_path / "checkout/scripts"
    scripts.mkdir(parents=True)
    launcher = scripts / "so101-macos.zsh"
    shutil.copyfile(root / "scripts/so101-macos.zsh", launcher)
    # Replace only the external doctor command to inspect its real child environment.
    (scripts / "so101_macos_runtime_contract.py").write_text(
        "import os; print(os.environ.get('SO101_IK_BACKEND', 'MISSING'))\n"
    )
    result = subprocess.run(
        ["/bin/zsh", str(launcher), "doctor", "--base"],
        env={**os.environ, "SO101_IK_BACKEND": "quik"},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "quik"
