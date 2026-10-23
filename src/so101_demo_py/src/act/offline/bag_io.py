"""Read and write rosbag2 MCAP bags without a live ROS graph (rosbag2_py only; no node, no publisher)."""

from __future__ import annotations

from pathlib import Path

STORAGE_ID = "mcap"


def _storage(uri: Path, storage_id: str = STORAGE_ID, storage_config_path=None):
    import rosbag2_py
    options = rosbag2_py.StorageOptions(uri=str(uri), storage_id=storage_id)
    if storage_config_path is not None:
        options.storage_config_uri = str(storage_config_path)
    return options


def mcap_chunk_compressions(path) -> set:
    """The compression names of every chunk record of one .mcap file ("" is uncompressed, "zstd", "lz4").

    Walks the record headers and seeks over the bodies, so a multi-gigabyte bag costs one small read per chunk. The messages
    themselves are read through rosbag2_py (`read_messages`), which decompresses chunks transparently."""
    import struct

    found = set()
    with open(path, "rb") as stream:
        if stream.read(8) != b"\x89MCAP0\r\n":
            raise ValueError("not an MCAP file")
        while True:
            header = stream.read(9)
            if len(header) < 9:
                break
            opcode, length = header[0], struct.unpack("<Q", header[1:])[0]
            if opcode == 0x0F:      # DataEnd: no chunk follows
                break
            if opcode == 0x06:      # Chunk: start u64, end u64, uncompressed size u64, crc u32, compression (u32 length + bytes)
                head = stream.read(32)
                size = struct.unpack("<I", head[28:32])[0]
                found.add(stream.read(size).decode("ascii"))
                stream.seek(length - 32 - size, 1)
            else:
                stream.seek(length, 1)
    return found


def bag_info(uri) -> dict:
    """The bag's own metadata: per-topic type and message count, first and last message time, duration."""
    import rosbag2_py

    metadata = rosbag2_py.Info().read_metadata(str(uri), STORAGE_ID)
    return {
        "message_count": int(metadata.message_count),
        "starting_time_ns": int(metadata.starting_time.nanoseconds),
        "duration_ns": int(metadata.duration.nanoseconds),
        "topics": {item.topic_metadata.name: {"type": item.topic_metadata.type, "count": int(item.message_count),
                                                "qos": item.topic_metadata.offered_qos_profiles}
                   for item in metadata.topics_with_message_count},
    }


def read_messages(uri, topics=None):
    """(topic, type name, bag timestamp ns, serialized bytes) in the bag's time order."""
    import rosbag2_py

    reader = rosbag2_py.SequentialReader()
    reader.open(_storage(Path(uri)), rosbag2_py.ConverterOptions("", ""))
    types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    if topics is not None:
        selected = [name for name in types if name in set(topics)]
        if topics and not selected:
            return
        reader.set_filter(rosbag2_py.StorageFilter(topics=selected))
    while reader.has_next():
        topic, data, stamp = reader.read_next()
        yield topic, types[topic], int(stamp), bytes(data)


class BagWriter:
    """A tiny writer for tests and synthetic bags: `create(topic, type)` then `write(topic, message, stamp_ns)`."""

    def __init__(self, uri, storage_config_path=None):
        import rosbag2_py

        self._writer = rosbag2_py.SequentialWriter()
        self._writer.open(_storage(Path(uri), storage_config_path=storage_config_path), rosbag2_py.ConverterOptions("cdr", "cdr"))
        self._topics = set()

    def create(self, topic: str, type_name: str, qos: str = "") -> None:
        import rosbag2_py

        if topic not in self._topics:
            self._writer.create_topic(rosbag2_py.TopicMetadata(id=len(self._topics), name=topic, type=type_name,
                                                                serialization_format="cdr", offered_qos_profiles=[]))
            self._topics.add(topic)

    def write(self, topic: str, message, stamp_ns: int) -> None:
        from rclpy.serialization import serialize_message

        self._writer.write(topic, serialize_message(message), int(stamp_ns))

    def write_serialized(self, topic: str, data: bytes, stamp_ns: int) -> None:
        self._writer.write(topic, data, int(stamp_ns))

    def close(self) -> None:
        del self._writer
