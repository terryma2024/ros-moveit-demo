"""MCAP chunk compression (zstd) is lossless: the same messages written with and without it read back identically (topic, type,
log_time, bytes, order), through the rosbag2 reader and through the offline readers, and the chunk compression is observable."""
import pathlib

import pytest

rclpy = pytest.importorskip("rclpy")
rosbag2_py = pytest.importorskip("rosbag2_py")
import yaml
from std_msgs.msg import String
from sensor_msgs.msg import Image

from so101_demo.act.offline.bag_io import BagWriter, bag_info, read_messages, mcap_chunk_compressions
from so101_demo.act.offline.raw_recorder import BAG_STORAGE_CONFIG

STAMP = 1_700_000_000_000_000_000


def _messages():
    """Serialized once: CDR padding bytes are not zeroed, so serializing the same message twice may differ in padding."""
    from rclpy.serialization import serialize_message
    out = []
    for index in range(40):
        out.append(("/z/text", serialize_message(String(data=f"m{index}")), STAMP + index * 1_000_003))
        image = Image(height=64, width=64, encoding="rgb8", step=192, data=bytes((index + n) % 7 for n in range(64 * 64 * 3)))
        out.append(("/z/image", serialize_message(image), STAMP + index * 1_000_003 + 17))
    return out


def _write(uri, config_path):
    writer = BagWriter(uri, storage_config_path=config_path)
    writer.create("/z/text", "std_msgs/msg/String")
    writer.create("/z/image", "sensor_msgs/msg/Image")
    for topic, data, stamp in MESSAGES:
        writer.write_serialized(topic, data, stamp)
    writer.close()


MESSAGES = _messages()


def _pair(tmp_path):
    config = tmp_path / "storage.yaml"
    config.write_text(yaml.safe_dump(BAG_STORAGE_CONFIG))
    _write(tmp_path / "plain", None)
    _write(tmp_path / "zstd", config)
    return tmp_path / "plain", tmp_path / "zstd"


def _mcap(directory):
    return next(directory.glob("*.mcap"))


def test_zstd_and_plain_bags_decode_identically_and_the_compression_is_observable(tmp_path):
    plain_dir, zstd_dir = _pair(tmp_path)
    plain, packed = list(read_messages(plain_dir)), list(read_messages(zstd_dir))
    assert len(plain) == 80 and packed == plain, "topic, type, log_time, bytes and order are identical"
    assert [item[2] for item in packed] == sorted(item[2] for item in packed)
    assert bag_info(plain_dir) == bag_info(zstd_dir)
    assert list(read_messages(zstd_dir, topics=["/z/text"])) == [m for m in plain if m[0] == "/z/text"]
    assert mcap_chunk_compressions(_mcap(plain_dir)) == {""}
    assert mcap_chunk_compressions(_mcap(zstd_dir)) == {"zstd"}
    assert _mcap(zstd_dir).stat().st_size < _mcap(plain_dir).stat().st_size


def test_the_offline_readers_do_not_read_mcap_bytes_directly(tmp_path):
    """Every offline reader opens a bag through bag_io (rosbag2_py), so compressed chunks are transparent to it."""
    import so101_demo.act.offline as offline
    for path in pathlib.Path(offline.__file__).parent.glob("*.py"):
        text = path.read_text()
        assert "import mcap" not in text and "from mcap" not in text, path
