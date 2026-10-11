"""The separately owned Teleop acceptance, with a teardown the receipt can prove.

The plan starts *one* new stack from the frozen install, the promoted config, the approved bundle, the
approval receipt and the closed head-only report; runs the installed unified app against that one stack
and its one detector; exercises the head-camera surface; and tears everything down before it writes
anything. The installed surface this module replaces wrote a connection descriptor immediately, ran no
probe and recorded ``teardown: not-attempted``.

What this module owns, in the plan's order and with no step optional:

1. read the frozen runtime's own identity off disk and refuse a runtime that is not the declared one;
2. verify the declared approved bundle against the promoted 17 values, and the socket paths against the
   AF_UNIX limit *before* anything is launched;
3. prove the pre-start process/ROS/GPU table empty, then start one production composition and its one
   CUDA detector, and measure the real head-camera frames it consumes;
4. publish the connection descriptor only after the probes pass, start the installed unified app against
   it, and record every head-camera probe (served, status, bounded absolute target, sealed interval,
   out-of-range refusal, no-frame and stale-frame capture refusals, the three-sample stop proof);
5. run the installed Playwright case and read *its own* on-disk evidence rather than a caller's claim;
6. stop the app and the stack, prove every owned process group gone and the GPU released, then write the
   teardown receipt, the bridge cleanup receipt and finally the acceptance receipt.

The receipt is the document the aggregate's ``teleop_acceptance`` gate consumes field by field. A closed
head-only report is a *precondition* the plan states and this module cannot invent: when it is absent the
acceptance still runs and records the truth, and the receipt says so in ``qualification_report`` and in
``refusals`` instead of claiming a report that does not exist.
"""
