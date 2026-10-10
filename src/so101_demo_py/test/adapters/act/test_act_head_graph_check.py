"""The polled endpoint-GID graph check (design section 2): any unexpected endpoint faults the run."""

import time

import pytest

from so101_demo.adapters.act.head_graph_check import HeadGraphCheck, RclpyGraph

FEEDBACK = '/neck_controller/follow_joint_trajectory/_action/feedback'
STATUS = '/neck_controller/follow_joint_trajectory/_action/status'
COMMAND = '/neck_controller/joint_trajectory'
SCALING = '/neck_controller/speed_scaling_input'
ARM_FEEDBACK = '/arm_controller/follow_joint_trajectory/_action/feedback'
GRIPPER_STATUS = '/gripper_controller/follow_joint_trajectory/_action/status'
SWITCH = '/controller_manager/switch_controller'
LIST = '/controller_manager/list_controllers'
OWN = 'head_run_r1'


class FakeGraph:
    def __init__(self):
        self.subs, self.pubs, self.clients = {}, {}, {}

    def add_sub(self, topic, node, gid):
        self.subs.setdefault(topic, []).append(dict(node_name=node, gid=gid))

    def add_pub(self, topic, node, gid):
        self.pubs.setdefault(topic, []).append(dict(node_name=node, gid=gid))

    def add_client(self, service, node):
        self.clients.setdefault(service, []).append(dict(node_name=node, gid=None))

    def subscriptions(self, topic):
        return [dict(row) for row in self.subs.get(topic, [])]

    def publishers(self, topic):
        return [dict(row) for row in self.pubs.get(topic, [])]

    def service_clients(self, service):
        return [dict(row) for row in self.clients.get(service, [])]


def baseline():
    graph = FakeGraph()
    graph.add_sub(FEEDBACK, OWN, 'aa01')
    graph.add_sub(STATUS, OWN, 'aa02')
    graph.add_client(SWITCH, OWN)
    graph.add_client(LIST, OWN)
    return graph


def check(graph, allowed=()):
    return HeadGraphCheck(graph=graph, own_node_name=OWN, allowed_node_names=allowed)


def test_the_startup_proof_records_the_runtimes_own_gids_and_the_audited_service_clients():
    graph = baseline()
    graph.add_client(SWITCH, 'some_cli_node')
    proof = check(graph).proof()
    assert proof['own_gids'] == {FEEDBACK: ['aa01'], STATUS: ['aa02']}
    assert proof['foreign_allowed'] == []
    assert sorted(client['node_name'] for client in proof['service_clients'][SWITCH]) == [OWN, 'some_cli_node']
    assert proof['watched']['neck_subscriptions'] == [FEEDBACK, STATUS]
    assert proof['watched']['neck_publishers'] == [COMMAND, SCALING]


def test_a_quiet_graph_polls_clean_and_repeatedly():
    graph = baseline()
    watcher = check(graph)
    watcher.proof()
    assert watcher.poll() is None and watcher.poll() is None


@pytest.mark.parametrize('topic', [FEEDBACK, STATUS])
def test_a_foreign_action_client_on_the_neck_changes_the_graph(topic):
    graph = baseline()
    watcher = check(graph)
    watcher.proof()
    graph.add_sub(topic, 'rogue_client', 'ff99')
    change = watcher.poll()
    assert change['code'] == 'HEAD_GRAPH_CHANGED'
    assert change['added'] == [dict(topic=topic, kind='subscription', node_name='rogue_client', gid='ff99')]
    assert watcher.changed == change


@pytest.mark.parametrize('topic', [COMMAND, SCALING])
def test_any_publisher_on_the_closed_command_and_scaling_topics_changes_the_graph(topic):
    graph = baseline()
    watcher = check(graph)
    watcher.proof()
    graph.add_pub(topic, 'rogue_publisher', 'ee01')
    change = watcher.poll()
    assert change['code'] == 'HEAD_GRAPH_CHANGED' and change['added'][0]['kind'] == 'publisher'


@pytest.mark.parametrize('topic', [ARM_FEEDBACK, GRIPPER_STATUS])
def test_a_foreign_client_of_the_arm_or_gripper_action_changes_the_graph(topic):
    graph = baseline()
    watcher = check(graph)
    watcher.proof()
    graph.add_sub(topic, 'moveit_stub', 'dd01')
    assert watcher.poll()['added'][0]['node_name'] == 'moveit_stub'


def test_an_allowlisted_recorder_is_allowed_and_recorded_not_faulted():
    graph = baseline()
    graph.add_sub(STATUS, 'raw_recorder', 'bb01')
    watcher = check(graph, allowed=('raw_recorder', '_ros2cli_bag'))
    proof = watcher.proof()
    assert proof['foreign_allowed'] == [dict(topic=STATUS, kind='subscription', node_name='raw_recorder', gid='bb01')]
    graph.add_sub(FEEDBACK, '_ros2cli_bag', 'bb02')
    assert watcher.poll() is None
    assert watcher.foreign_allowed_seen == [
        dict(topic=STATUS, kind='subscription', node_name='raw_recorder', gid='bb01'),
        dict(topic=FEEDBACK, kind='subscription', node_name='_ros2cli_bag', gid='bb02')]


def test_the_own_node_name_is_not_enough_a_new_gid_from_the_own_name_is_a_change():
    graph = baseline()
    watcher = check(graph)
    watcher.proof()
    graph.add_sub(FEEDBACK, OWN, 'aa77')  # same node name, a gid the runtime did not record at startup
    change = watcher.poll()
    assert change['added'][0]['gid'] == 'aa77'


def test_service_clients_of_the_controller_manager_are_audited_not_faulted():
    graph = baseline()
    watcher = check(graph)
    watcher.proof()
    graph.add_client(SWITCH, 'ros2_cli_tool')
    assert watcher.poll() is None
    assert [row['node_name'] for row in watcher.audited_clients[SWITCH]] == [OWN, 'ros2_cli_tool']


def test_a_removed_own_endpoint_is_also_a_change():
    graph = baseline()
    watcher = check(graph)
    watcher.proof()
    graph.subs[FEEDBACK] = []
    change = watcher.poll()
    assert change['code'] == 'HEAD_GRAPH_CHANGED' and change['removed'] == [
        dict(topic=FEEDBACK, kind='subscription', node_name=OWN, gid='aa01')]


def test_a_foreign_endpoint_already_present_at_startup_refuses_the_proof():
    graph = baseline()
    graph.add_sub(ARM_FEEDBACK, 'moveit_stub', 'dd01')
    with pytest.raises(PermissionError, match='HEAD_GRAPH_FOREIGN_ENDPOINT'):
        check(graph).proof()


def test_poll_before_the_proof_is_refused_and_the_change_latches():
    graph = baseline()
    watcher = check(graph)
    with pytest.raises(PermissionError, match='HEAD_GRAPH_PROOF_REQUIRED'):
        watcher.poll()
    watcher.proof()
    graph.add_sub(STATUS, 'rogue', 'ff01')
    first = watcher.poll()
    graph.subs[STATUS] = [row for row in graph.subs[STATUS] if row['node_name'] != 'rogue']
    assert watcher.poll() == first, 'a graph change stays latched even if the endpoint goes away'


# ---- the real rclpy graph ----------------------------------------------------------------------------------

def test_the_rclpy_graph_reports_node_names_and_endpoint_gids(isolated_ros_domain):
    import rclpy
    from rclpy.context import Context
    from std_msgs.msg import String
    context = Context()
    rclpy.init(context=context)
    try:
        own = rclpy.create_node(OWN, context=context)
        rogue = rclpy.create_node('rogue_publisher', context=context)
        own.create_subscription(String, FEEDBACK, lambda message: None, 10)
        rogue.create_publisher(String, COMMAND, 10)
        deadline = time.monotonic() + 5.
        graph = RclpyGraph(own)
        while time.monotonic() < deadline and not (graph.publishers(COMMAND) and graph.subscriptions(FEEDBACK)):
            time.sleep(.05)
        subs, pubs = graph.subscriptions(FEEDBACK), graph.publishers(COMMAND)
        assert [row['node_name'] for row in subs] == [OWN]
        assert [row['node_name'] for row in pubs] == ['rogue_publisher']
        assert all(isinstance(row['gid'], str) and len(row['gid']) >= 16 for row in subs + pubs)
        assert subs[0]['gid'] != pubs[0]['gid']
        watcher = HeadGraphCheck(graph=graph, own_node_name=OWN)
        with pytest.raises(PermissionError, match='HEAD_GRAPH_FOREIGN_ENDPOINT'):
            watcher.proof()
    finally:
        context.shutdown()
