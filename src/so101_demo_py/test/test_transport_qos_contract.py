from pathlib import Path
from xml.etree import ElementTree

import yaml
from so101_demo.backends.mujoco.transport_observer import RELIABLE_QOS_DEPTH

PACKAGE = Path(__file__).resolve().parents[1]


def test_reliable_consumer_retains_at_least_the_producer_history() -> None:
    assert RELIABLE_QOS_DEPTH >= 100


def test_lossless_chunk_rate_is_bounded_for_durable_tmp_evidence() -> None:
    plugin_config = yaml.safe_load(
        (PACKAGE / "config/mujoco/mujoco_plugins.yaml").read_bytes()
    )["/**"]["ros__parameters"]
    chunk_size = int(plugin_config["physics_step_chunk_size"])
    buffer_capacity = int(plugin_config["physics_step_buffer_capacity"])

    option = ElementTree.parse(PACKAGE / "assets/mujoco/scene.xml").getroot().find(
        "option"
    )
    assert option is not None
    physics_timestep_s = float(option.attrib["timestep"])
    durable_chunk_rate_hz = 1.0 / (physics_timestep_s * chunk_size)

    assert chunk_size <= buffer_capacity
    assert durable_chunk_rate_hz <= 10.0
