"""The ACT scene's own identity, derived from the file and the compiled model (never pasted into tests)."""
import hashlib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
ACT_SCENE = PACKAGE / "assets/mujoco/act/scene.xml"


def _derive():
    import mujoco
    from so101_demo.adapters.act.physics import model_sha256

    return (hashlib.sha256(ACT_SCENE.read_bytes()).hexdigest(),
            model_sha256(mujoco.MjModel.from_xml_path(str(ACT_SCENE))))


ACT_SCENE_SHA256, ACT_MODEL_SHA256 = _derive()
