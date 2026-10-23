"""The polled graph check (design section 2): endpoint GIDs of the neck's closed inputs.

The stock action server cannot tell its clients apart, so owner-only admission does not authenticate action
clients. This check compensates by watching the endpoints that matter:

* subscriptions on the neck's action ``feedback`` and ``status`` topics (every action client has them);
* publishers on ``~/joint_trajectory`` and the speed-scaling topic, which must stay closed;
* subscriptions on the arm and gripper action topics, which must have no foreign client.

The allowed endpoints are this runtime's own GIDs recorded at startup, plus subscriptions of nodes on an
allowlist by node name (the raw recorder, ``ros2 bag``), which are recorded and never fault. Clients of the
controller manager's ``switch_controller`` and ``list_controllers`` are audited by node, not faulted. Any other
change faults the run with ``HEAD_GRAPH_CHANGED`` and stays latched.
"""

CODE = 'HEAD_GRAPH_CHANGED'

NECK_SUBSCRIPTIONS = ('/neck_controller/follow_joint_trajectory/_action/feedback',
                      '/neck_controller/follow_joint_trajectory/_action/status')
NECK_PUBLISHERS = ('/neck_controller/joint_trajectory', '/neck_controller/speed_scaling_input')
OTHER_CLIENT_SUBSCRIPTIONS = (
    '/arm_controller/follow_joint_trajectory/_action/feedback',
    '/arm_controller/follow_joint_trajectory/_action/status',
    '/gripper_controller/follow_joint_trajectory/_action/feedback',
    '/gripper_controller/follow_joint_trajectory/_action/status')
CONTROLLER_MANAGER_SERVICES = ('/controller_manager/switch_controller',
                               '/controller_manager/list_controllers')


def _gid_hex(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    return ''.join('%02x' % (item & 0xff) for item in value)


class RclpyGraph:
    """The rclpy graph as dictionaries: node name and endpoint GID."""

    def __init__(self, node):
        self.node = node

    @staticmethod
    def _rows(infos):
        return [dict(node_name=info.node_name, gid=_gid_hex(info.endpoint_gid)) for info in infos]

    def subscriptions(self, topic):
        return self._rows(self.node.get_subscriptions_info_by_topic(topic))

    def publishers(self, topic):
        return self._rows(self.node.get_publishers_info_by_topic(topic))

    def service_clients(self, service):
        rows = []
        for name, namespace in self.node.get_node_names_and_namespaces():
            try:
                clients = self.node.get_client_names_and_types_by_node(name, namespace)
            except Exception:
                continue
            if any(client == service for client, _ in clients):
                rows.append(dict(node_name=name, gid=None))
        return rows


class HeadGraphCheck:
    def __init__(self, *, graph, own_node_name, allowed_node_names=()):
        self.graph = graph
        self.own_node_name = own_node_name
        self.allowed_node_names = frozenset(allowed_node_names)
        self._own = None            # {(topic, kind): set(gid)} recorded at startup
        self.changed = None
        self.foreign_allowed_seen = []
        self.audited_clients = {}
        self.polls = 0

    # ---- one scan -----------------------------------------------------------------------------------

    def _scan(self):
        endpoints = []
        for topic in NECK_SUBSCRIPTIONS + OTHER_CLIENT_SUBSCRIPTIONS:
            endpoints += [dict(topic=topic, kind='subscription', **row)
                          for row in self.graph.subscriptions(topic)]
        for topic in NECK_PUBLISHERS:
            endpoints += [dict(topic=topic, kind='publisher', **row) for row in self.graph.publishers(topic)]
        clients = {service: self.graph.service_clients(service) for service in CONTROLLER_MANAGER_SERVICES}
        return endpoints, clients

    def _is_own(self, endpoint):
        return (endpoint['topic'] in NECK_SUBSCRIPTIONS and endpoint['kind'] == 'subscription'
                and endpoint['node_name'] == self.own_node_name)

    def _classify(self, endpoints):
        own, allowed, foreign = [], [], []
        for endpoint in endpoints:
            if self._is_own(endpoint):
                own.append(endpoint)
            elif endpoint['kind'] == 'subscription' and endpoint['node_name'] in self.allowed_node_names:
                allowed.append(endpoint)
            else:
                foreign.append(endpoint)
        return own, allowed, foreign

    # ---- startup proof and polling ---------------------------------------------------------------------

    def proof(self):
        endpoints, clients = self._scan()
        own, allowed, foreign = self._classify(endpoints)
        if foreign:
            raise PermissionError('HEAD_GRAPH_FOREIGN_ENDPOINT: ' + ', '.join(
                f"{row['kind']} {row['topic']} by {row['node_name']}" for row in foreign))
        self._own = {}
        for endpoint in own:
            self._own.setdefault(endpoint['topic'], []).append(endpoint['gid'])
        self.foreign_allowed_seen = [dict(row) for row in allowed]
        self.audited_clients = {service: [dict(row) for row in rows] for service, rows in clients.items()}
        return dict(own_gids={topic: sorted(gids) for topic, gids in sorted(self._own.items())},
                    foreign_allowed=[dict(row) for row in allowed],
                    service_clients={service: [dict(row) for row in rows] for service, rows in clients.items()},
                    allowed_node_names=sorted(self.allowed_node_names),
                    watched=dict(neck_subscriptions=list(NECK_SUBSCRIPTIONS),
                                 neck_publishers=list(NECK_PUBLISHERS),
                                 other_client_subscriptions=list(OTHER_CLIENT_SUBSCRIPTIONS)))

    def poll(self):
        """Compare with the proof; returns the (latched) change, or None."""
        if self._own is None:
            raise PermissionError('HEAD_GRAPH_PROOF_REQUIRED')
        if self.changed is not None:
            return self.changed
        self.polls += 1
        endpoints, clients = self._scan()
        own, allowed, foreign = self._classify(endpoints)
        for row in allowed:
            if row not in self.foreign_allowed_seen:
                self.foreign_allowed_seen.append(dict(row))
        self.audited_clients = {service: [dict(row) for row in rows] for service, rows in clients.items()}
        added = [dict(row) for row in foreign]
        removed = []
        current = {}
        for row in own:
            current.setdefault(row['topic'], set()).add(row['gid'])
        for topic, gids in self._own.items():
            for gid in gids:
                if gid not in current.get(topic, set()):
                    removed.append(dict(topic=topic, kind='subscription', node_name=self.own_node_name, gid=gid))
        for topic, gids in current.items():
            for gid in sorted(gids - set(self._own.get(topic, []))):
                added.append(dict(topic=topic, kind='subscription', node_name=self.own_node_name, gid=gid))
        if added or removed:
            self.changed = dict(code=CODE, added=added, removed=removed)
        return self.changed
