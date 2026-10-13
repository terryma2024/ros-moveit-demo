"""Real MCAP readback: topic names, counts, payload order and the topic filter of `bag_io` and the replay stream."""

from std_msgs.msg import String

from so101_demo.act.offline.bag_io import BagWriter, bag_info, read_messages


def test_read_messages_keeps_names_counts_payload_order_and_filters(tmp_path):
    topics = ("/clock", "/so101/teacher/events")
    bag = tmp_path / "bag"
    writer = BagWriter(bag)
    for name in topics:
        writer.create(name, "std_msgs/msg/String")
    for number in range(4):
        writer.write(topics[number % 2], String(data=str(number)), 100 + number)
    del writer
    info = bag_info(bag)
    assert set(info["topics"]) == set(topics) and info["message_count"] == 4
    assert all(value["count"] == 2 for value in info["topics"].values())
    rows = list(read_messages(bag))
    assert [row[0] for row in rows] == [topics[number % 2] for number in range(4)]
    assert [row[2] for row in rows] == [100, 101, 102, 103]
    assert len(list(read_messages(bag, topics=[topics[1]]))) == 2
    assert list(read_messages(bag, topics=["/missing"])) == []
    from rclpy.serialization import deserialize_message
    assert [deserialize_message(row[3], String).data for row in rows] == ["0", "1", "2", "3"]


def test_replay_stream_delivers_every_topic_and_honours_the_topic_filter(tmp_path):
    from offline_synthetic_bag import build_bag
    from so101_demo.act.offline import replay
    from so101_demo.act.offline.processor import load_clock_map

    bag = build_bag(tmp_path / "baseline")
    topics = tuple(bag_info(bag)["topics"])
    clock_map, _ = load_clock_map(bag)
    stream = replay.BagStream(bag, clock_map)
    seen = set()
    while (message := stream.pop()) is not None:
        seen.add(message.topic)
    assert seen == set(topics)
    filtered = replay.BagStream(bag, clock_map, topics=["/so101/teacher/events"])
    first = filtered.peek()
    assert first is not None and first.topic == "/so101/teacher/events"
