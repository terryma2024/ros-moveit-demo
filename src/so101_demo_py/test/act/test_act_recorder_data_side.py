"""REPLACED_BY `test_recorder_data_side_teacher_events.py` (B2, plan R9.9).

This file held the data-side consumer tests of the V1 stream: the reset boundary carried by `phase_begin`, the native
dispatch receipt (UUID, permit and CDR checks), and the expert `sequence_complete` boundary. Those contracts are gone:
the verified reset is the `reset_complete` event, the first command is the first goal-sending `phase_begin`, and the
normal end is `normal_stop` followed by `terminal`. Every surviving fault (reset original changed, foreign scope, receipt
after the clock, event sequence, the initial boundary after the first command) is a test in `test_recorder_data_side_teacher_events.py`.
"""
