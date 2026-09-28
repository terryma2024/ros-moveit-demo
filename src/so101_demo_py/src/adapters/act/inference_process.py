"""Task 13: keep inference off the control loop, and never apply a late answer.

The boundary admits one request at a time. A reply that does not match the in-flight sequence, or that
arrived later than the configured age allows, is refused rather than applied: an action chunk computed for
a moment that has passed would command the arm with stale intent.
"""

from __future__ import annotations


class ActInferenceProcess:
    """A one-in-flight request boundary over an injected transport."""

    def __init__(self, *, config: dict, transport, clock) -> None:
        inference = config.get("inference") if isinstance(config, dict) else None
        if not isinstance(inference, dict) or inference.get("device") != "cuda":
            raise ValueError("INFERENCE_CONFIG_INVALID")
        for field in ("request_timeout_s", "max_reply_age_s"):
            value = inference.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError("INFERENCE_CONFIG_INVALID")
        if not callable(getattr(transport, "send", None)) or not callable(getattr(transport, "close", None)):
            raise ValueError("INFERENCE_TRANSPORT_REQUIRED")
        self.config = config
        self.inference = inference
        self.transport = transport
        self.clock = clock
        self.pending = None
        self.closed = False

    def submit(self, observation: dict, *, sequence: int) -> int:
        """Admit one request; a second request while one is in flight is refused, not queued."""

        if self.closed:
            raise ValueError("INFERENCE_PROCESS_CLOSED")
        if not isinstance(observation, dict) or not observation:
            raise ValueError("INFERENCE_OBSERVATION_INVALID")
        if type(sequence) is not int or sequence < 0:
            raise ValueError("INFERENCE_SEQUENCE_INVALID")
        if self.pending is not None:
            raise ValueError("INFERENCE_REQUEST_IN_FLIGHT")
        deadline = self.clock() + float(self.inference["request_timeout_s"])
        self.transport.send({"sequence": sequence, "observation": observation})
        self.pending = {"sequence": sequence, "deadline": deadline}
        return sequence

    def poll(self) -> dict:
        """Take the reply for the in-flight request, or refuse with the reason it is unusable."""

        if self.closed:
            raise ValueError("INFERENCE_PROCESS_CLOSED")
        if self.pending is None:
            raise ValueError("INFERENCE_NO_REQUEST")
        reply = self.transport.receive() if callable(getattr(self.transport, "receive", None)) else None
        if reply is None:
            if self.clock() >= self.pending["deadline"]:
                raise ValueError("INFERENCE_TIMEOUT")
            return {}
        if not isinstance(reply, dict) or "sequence" not in reply or "actions" not in reply:
            raise ValueError("INFERENCE_REPLY_INVALID")
        if reply["sequence"] != self.pending["sequence"]:
            # a reply for another sequence cannot describe this observation
            raise ValueError("INFERENCE_REPLY_OUT_OF_ORDER")
        age = float(reply.get("age_s", 0.0))
        if isinstance(reply.get("age_s"), bool) or not isinstance(reply.get("age_s", 0.0), (int, float)):
            raise ValueError("INFERENCE_REPLY_INVALID")
        if age > float(self.inference["max_reply_age_s"]):
            raise ValueError("INFERENCE_REPLY_STALE")
        self.pending = None
        return {"sequence": reply["sequence"], "actions": reply["actions"], "age_s": age}

    def close(self) -> None:
        """Close the worker; a boundary that cannot close reports it rather than leaving an orphan."""

        if self.closed:
            return
        outcome = self.transport.close()
        if outcome is False:
            raise ValueError("INFERENCE_PROCESS_STILL_RUNNING")
        self.closed = True
        self.pending = None
