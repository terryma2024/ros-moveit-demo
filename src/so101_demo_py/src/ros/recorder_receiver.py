"""The Recorder's main-node receiver: the node's callbacks run on their own thread, not on the loop's cadence.

The Recorder loop used to serve its node with `spin_burst` once per pass, so every main-node receipt (world evidence, scene
state, controller states, joint states, camera frames, Teacher events) was stamped when the loop next came round, and a
loop pass of 100-250 ms (L2: seen five times in 12 s) aged all of them at once. The same node is now served by a
`SingleThreadedExecutor` on a dedicated thread, exactly as the chunk spooler's reader and the physics adapter's former private
node do: a receipt is stamped when the message is delivered, and the loop only reads what the receiver has already kept.

The receiver stamps and keeps; it decides nothing. Every structure its callbacks write is locked by its owner (the observers,
the capture's ingress lock, the controller history, the engine inbox).
"""

from __future__ import annotations

import collections
import threading


class NodeReceiver:
    def __init__(self, node, *, executor=None, period_s: float = 0.05) -> None:
        self.node, self._executor, self._period_s = node, executor, period_s
        self._stop = threading.Event()
        self._thread = None
        self._error = None
        self._callback_errors = collections.deque(maxlen=16)
        self._callback_error_total = 0
        self._spins = 0

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("RECORDER_RECEIVER_ALREADY_STARTED")
        if self._executor is None:
            from rclpy.executors import SingleThreadedExecutor

            self._executor = SingleThreadedExecutor(context=self.node.context)
        self._executor.add_node(self.node)
        self._thread = threading.Thread(target=self._loop, name="so101-recorder-node-receiver", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        """Serve the node until stopped. A callback that raises is one more reason the data is invalid (the loop reports it
        through `take_callback_errors`, as `spin_burst` used to raise it from the pump), never the end of the receiver."""
        while not self._stop.is_set():
            try:
                self._executor.spin_once(timeout_sec=self._period_s)
                self._spins += 1
            except BaseException as error:  # noqa: BLE001
                if self._stop.is_set():
                    return
                if self._context_gone() or not isinstance(error, Exception):
                    self._error = f"{type(error).__name__}: {error}"[:300]
                    return
                self._callback_error_total += 1
                self._callback_errors.append(f"{type(error).__name__}: {error}"[:300])

    def _context_gone(self) -> bool:
        try:
            return not self.node.context.ok()
        except BaseException:  # noqa: BLE001 - a node without a context is a test double
            return False

    def take_callback_errors(self) -> list:
        errors = []
        while self._callback_errors:
            errors.append(self._callback_errors.popleft())
        return errors

    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self._error is None

    def failure(self):
        if self._error is not None:
            return self._error
        if self._thread is not None and not self._thread.is_alive() and not self._stop.is_set():
            return "RECORDER_RECEIVER_EXITED"
        return None

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        try:
            self._executor.remove_node(self.node)
        except BaseException:  # noqa: BLE001 - already removed or the context is gone
            pass
        try:
            self._executor.shutdown()
        except BaseException:  # noqa: BLE001
            pass
        if thread is not None and thread.is_alive():
            raise RuntimeError("RECORDER_RECEIVER_JOIN_TIMEOUT")

    def stats(self) -> dict:
        return {"spins": self._spins, "error": self._error, "callback_errors": self._callback_error_total}
