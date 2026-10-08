"""Contacts-consumer throughput bench (plan A22). Not a test module: test_act_contact_throughput.py runs it in a child
process with an isolated ROS domain. Env: A22_RATE (0 = burst), A22_GIL (none|hash|pyloop|mj), A22_N, A22_CONTACTS."""
import hashlib, os, sys, threading, time, multiprocessing as mp

DOMAIN = os.environ.get("A22_DOMAIN", "97")
N = int(os.environ.get("A22_N", "3000"))
CONTACTS = int(os.environ.get("A22_CONTACTS", "12"))
GIL_LOAD = os.environ.get("A22_GIL", "none")  # none | hash | mj
GEOMS = ["g%d" % i for i in range(40)]


def msg_fields(step, session="s"):
    return dict(simulation_session_id=session, reset_epoch=1, physics_step=step, simulation_time_s=step * .002,
                geom_a=[GEOMS[i] for i in range(CONTACTS)], geom_b=[GEOMS[39 - i] for i in range(CONTACTS)],
                signed_distance_m=[0.01 * i for i in range(CONTACTS)], normal_force_n=[1.0 + i for i in range(CONTACTS)],
                truncated=False, evidence_loss=False)


def publisher(rate_hz, count, ready, go):
    os.environ["ROS_DOMAIN_ID"] = DOMAIN
    import rclpy
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from so101_mujoco_support.msg import RobotContactEvidence
    rclpy.init()
    node = rclpy.create_node("a22_pub")
    pub = node.create_publisher(RobotContactEvidence, "/so101/simulation/robot_contacts",
                                QoSProfile(depth=10000, reliability=ReliabilityPolicy.RELIABLE))
    ready.set(); go.wait(30)
    deadline = time.monotonic() + 30
    while pub.get_subscription_count() < 1 and time.monotonic() < deadline:  # wait for discovery: volatile QoS drops earlier messages
        time.sleep(0.05)
    msgs = []
    for step in range(1, count + 1):
        m = RobotContactEvidence()
        for k, v in msg_fields(step).items():
            setattr(m, k, v)
        msgs.append(m)
    period = 1.0 / rate_hz if rate_hz else 0
    t0 = time.perf_counter()
    for i, m in enumerate(msgs):
        if period:
            while time.perf_counter() < t0 + i * period:
                pass
        pub.publish(m)
    time.sleep(1.0)
    rclpy.shutdown()


def gil_load(kind, stop):
    if kind == "hash":
        data = os.urandom(1 << 20)
        while not stop.is_set():
            h = hashlib.sha256()
            for _ in range(200):  # python-level chunk loop like provenance hashing (releases GIL inside hashlib for big blocks)
                h.update(data)
    elif kind == "pyloop":
        x = 0
        while not stop.is_set():
            for i in range(200000):
                x += i * i
    elif kind == "mj":
        import mujoco, numpy as np
        xml = "<mujoco><worldbody><geom type='sphere' size='.1'/><body pos='0 0 1'><freejoint/><geom type='box' size='.1 .1 .1'/></body></worldbody></mujoco>"
        model = mujoco.MjModel.from_xml_string(xml); data = mujoco.MjData(model)
        while not stop.is_set():
            data.qpos[:] = np.random.rand(model.nq)
            mujoco.mj_fwdPosition(model, data)


def consumer(rate_hz, count):
    sys.setswitchinterval(float(os.environ.get("A22_SWITCH", "0.005")))
    os.environ["ROS_DOMAIN_ID"] = DOMAIN
    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
    from so101_demo.adapters.act.contact_evidence import RobotContactObserver, RosRobotContactAdapter
    rclpy.init()
    node = rclpy.create_node("a22_sub")
    observer = RobotContactObserver(known_geoms=set(GEOMS), allowed_pairs={tuple(sorted((GEOMS[i], GEOMS[39 - i]))) for i in range(CONTACTS)},
                                    max_age_s=.5, max_sim_gap_s=.003, audit_integrity=True)
    observer.reset("s", 1, source_floor_s=0.)
    group = MutuallyExclusiveCallbackGroup()
    adapter = RosRobotContactAdapter(node, observer, on_hazard=lambda reason: print("HAZARD", reason, flush=True), callback_group=group)
    adapter._armed = True
    cost = [0.0, 0, None, None]
    original = adapter.accept_message
    def timed(message):
        t = time.perf_counter()
        original(message)
        now = time.perf_counter()
        cost[0] += now - t; cost[1] += 1
        if cost[2] is None: cost[2] = t
        cost[3] = now
    adapter.accept_message = timed  # the subscription callback (adapter._on_message or accept_message) calls this
    executor = MultiThreadedExecutor(num_threads=2); executor.add_node(node)
    spin = threading.Thread(target=executor.spin, daemon=True); spin.start()
    stop = threading.Event()
    if GIL_LOAD != "none":
        threading.Thread(target=gil_load, args=(GIL_LOAD, stop), daemon=True).start()
    ctx = mp.get_context("spawn"); ready, go = ctx.Event(), ctx.Event()
    proc = ctx.Process(target=publisher, args=(rate_hz, count, ready, go)); proc.start()
    ready.wait(60); time.sleep(1.5)  # discovery
    t_go = time.perf_counter(); go.set()
    last = 0; last_change = time.perf_counter()
    while time.perf_counter() - t_go < 90:
        time.sleep(0.02)
        if cost[1] != last:
            last = cost[1]; last_change = time.perf_counter()
        if cost[1] >= count or time.perf_counter() - last_change > 4:
            break
    stop.set()
    received = cost[1]
    span = (cost[3] - cost[2]) if received > 1 else float("nan")
    print("A22_DRAINED", getattr(adapter, "drained", None), flush=True)
    print("A22_RESULT switch=%s rate_hz=%s gil=%s contacts=%d received=%d/%d span_s=%.3f sustained_hz=%.1f callback_us=%.1f accept_cpu_share=%.2f"
          % (sys.getswitchinterval(), rate_hz or "burst", GIL_LOAD, CONTACTS, received, count, span, (received - 1) / span, cost[0] / max(received, 1) * 1e6,
             cost[0] / span), flush=True)
    proc.join(10)
    executor.shutdown(); rclpy.shutdown()


if __name__ == "__main__":
    mp.freeze_support()
    consumer(int(os.environ.get("A22_RATE", "0")), N)
