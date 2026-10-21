"""The registry of the ROS nodes a process keeps between calls: one call closes them all, never fails, and holds its holders weakly."""

import gc

from so101_demo.ros.kept_nodes import _holders, register_kept_ros_nodes, release_kept_ros_nodes


class Holder:
    def __init__(self, fail=False):
        self.released, self.fail = 0, fail

    def release(self):
        self.released += 1
        if self.fail:
            raise RuntimeError("cannot close")


def test_release_asks_every_registered_holder_and_counts_them():
    first, second = Holder(), Holder()
    register_kept_ros_nodes(first)
    register_kept_ros_nodes(second)
    assert release_kept_ros_nodes() >= 2
    assert (first.released, second.released) == (1, 1)
    release_kept_ros_nodes()
    assert (first.released, second.released) == (2, 2)      # a holder stays registered: it reopens and may be released again


def test_a_holder_that_fails_does_not_stop_the_others_or_the_caller():
    broken, fine = Holder(fail=True), Holder()
    register_kept_ros_nodes(broken)
    register_kept_ros_nodes(fine)
    release_kept_ros_nodes()
    assert broken.released == 1 and fine.released == 1


def test_a_holder_that_is_gone_is_not_asked_and_not_kept_alive():
    holder = Holder()
    register_kept_ros_nodes(holder)
    before = len(_holders)
    del holder
    gc.collect()
    assert len(_holders) == before - 1
    release_kept_ros_nodes()


def test_the_real_holders_register_themselves():
    from so101_demo.backends.mujoco.teleop_runtime import RetainedEvidence

    reader = RetainedEvidence("any-session")
    assert reader in _holders
