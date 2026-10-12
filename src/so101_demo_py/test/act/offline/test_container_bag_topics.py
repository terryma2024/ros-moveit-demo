"""Real MCAP readback of scoped channels; original logical source contracts stay intact."""

import importlib
import json

import pytest
from std_msgs.msg import String

from so101_demo.act.offline.bag_io import BagWriter,bag_info,read_messages


def fixture(tmp_path):
    root=tmp_path/'w00/g1';root.mkdir(parents=True)
    namespace='/act/campaign/w00'
    (root/'runtime-ready.json').write_text(json.dumps(dict(schema_version=1,kind='ACT_SHARD_RUNTIME_READY',
        generation=1,ros_namespace=namespace)))
    raw=root/'attempts/scene/attempt/working/raw';raw.mkdir(parents=True)
    return root,namespace,raw/'bag'


def test_scoped_mcap_preserves_logical_topics_counts_payload_order_and_filters(tmp_path):
    module=importlib.import_module('so101_demo.act.offline.container_bag_topics')
    root,namespace,bag=fixture(tmp_path)
    logical=('/clock','/so101/teacher/events')
    mapping=module.write_topic_map(bag,owned_root=root,namespace=namespace,topics=logical)
    writer=BagWriter(bag)
    for name in logical:writer.create(mapping[name],'std_msgs/msg/String')
    for number in range(4):
        name=logical[number%2]
        writer.write(mapping[name],String(data=str(number)),100+number)
    del writer
    info=bag_info(bag)
    assert set(info['topics'])==set(logical) and info['message_count']==4
    assert all(value['count']==2 for value in info['topics'].values())
    rows=list(read_messages(bag))
    assert [row[0] for row in rows]==[logical[number%2] for number in range(4)]
    assert [row[2] for row in rows]==[100,101,102,103]
    assert len(list(read_messages(bag,topics=[logical[1]])))==2
    assert list(read_messages(bag,topics=['/missing']))==[]
    from rclpy.serialization import deserialize_message
    assert [deserialize_message(row[3],String).data for row in rows]==['0','1','2','3']
    with pytest.raises(FileExistsError):
        module.write_topic_map(bag,owned_root=root,namespace=namespace,topics=logical)


@pytest.mark.parametrize('gap',[False,True])
def test_original_source_scan_recomputes_identical_full_counts_and_gaps_for_scoped_bag(tmp_path,monkeypatch,gap):
    from offline_synthetic_bag import build_bag
    from so101_demo.act.offline.scan import scan_bag
    import offline_synthetic_bag
    root,namespace,scoped=fixture(tmp_path)
    drop=(('/arm_controller/controller_state',200),) if gap else ()
    baseline=build_bag(tmp_path/'baseline',drop=drop)
    topics=tuple(bag_info(baseline)['topics'])
    module=importlib.import_module('so101_demo.act.offline.container_bag_topics')
    mapping=module.write_topic_map(scoped,owned_root=root,namespace=namespace,topics=topics)
    class ScopedWriter(BagWriter):
        def create(self,topic,type_name,qos=''):return super().create(mapping[topic],type_name,qos)
        def write(self,topic,message,stamp_ns):return super().write(mapping[topic],message,stamp_ns)
    monkeypatch.setattr(offline_synthetic_bag,'BagWriter',ScopedWriter)
    build_bag(scoped.parent,drop=drop)
    original=scan_bag(baseline,transport_lost=0,scene_reads_expected=1)
    actual=scan_bag(scoped,transport_lost=0,scene_reads_expected=1)
    assert actual==original
    if gap:assert original['reasons']


@pytest.mark.parametrize('problem',['foreign_root','ready_namespace','foreign_channel','duplicate_channel'])
def test_bad_source_bindings_or_channels_fail_closed(tmp_path,problem):
    module=importlib.import_module('so101_demo.act.offline.container_bag_topics')
    root,namespace,bag=fixture(tmp_path)
    if problem=='foreign_root':
        other=tmp_path/'foreign';other.mkdir()
        with pytest.raises(ValueError):module.write_topic_map(bag,owned_root=other,namespace=namespace,topics=('/clock',))
        return
    if problem=='ready_namespace':
        with pytest.raises(ValueError):module.write_topic_map(bag,owned_root=root,namespace='/act/foreign/w00',topics=('/clock',))
        return
    mapping=module.write_topic_map(bag,owned_root=root,namespace=namespace,topics=('/clock',))
    writer=BagWriter(bag)
    name='/foreign/clock' if problem=='foreign_channel' else mapping['/clock']
    writer.create(name,'std_msgs/msg/String');writer.write(name,String(data='one'),100)
    del writer
    if problem=='duplicate_channel':
        path=bag.parent/(bag.name+'-topic-map.json')
        document=json.loads(path.read_bytes());document['topics']['/another']=mapping['/clock']
        path.write_text(json.dumps(document))
    with pytest.raises(ValueError):bag_info(bag)
    with pytest.raises(ValueError):list(read_messages(bag))
