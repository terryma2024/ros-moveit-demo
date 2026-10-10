# Head event logging

Set the optional top-level `event_log_enabled` field in the Head execution-input
JSON before starting a run:

```json
"event_log_enabled": false
```

The field accepts JSON booleans only. Omitting it enables logging. Each run uses
the value from its verified input document; changing modes requires a new run.
Keep the existing input references, resource declarations and safety budgets.

With logging enabled, omitting `save_all_rgb_frames` or setting it to `false`
retains only the original RGB frames submitted to the detector. This field
accepts JSON booleans and defaults to `false`. Detection-only mode also saves
inputs that return no detections or raise a detector error. Frames rejected
before detection are not saved.

Set `save_all_rgb_frames` explicitly to `true` to save every RGB frame received
during capture. Existing input documents that omit this field now use
detection-only saving; add `true` when full-frame evidence is required.

`event_log_enabled: false` disables RGB evidence in either saving mode. The
frame-saving switch changes file retention; the camera still delivers images
and the detector still processes admitted frames. Functional campaign runs use
logging enabled and `save_all_rgb_frames: false`; turn full-frame saving on in a
separate run when debugging needs it.

Run the installed entry with the complete input document:

```sh
so101_head_search_calibration run --execution-inputs /abs/execution-inputs.json
```

With logging disabled, the entry creates no `HeadRunEvidence`, event writer
thread, evidence queues, manifest, `events.jsonl`, artifact directory, completion
file or seal. It skips event argument construction, audit copies, diagnostic
histories and logging hashes at their producers. Camera bytes still reach the
detector, but the logger saves no RGB copy. Owned child output goes to
`/dev/null` without a child log file or capture handle.

This removes work dedicated to Head event evidence. The switch still needs a
branch. Control, perception, input verification, original-frame integrity checks,
native protocol files, execution snapshots and ROS parameter files retain their
normal costs. ROS and other libraries can still format their own messages;
this field does not configure their internal loggers. CLI error output and an
explicit `--print-readback` request also remain available.

Freshness checks, immutable deadlines, fault latching, native close, cancellation,
raw Stop and resource retirement run in both modes. Exit codes remain `0` for
success, `1` for a business or runtime failure, and `2` for input or provider
refusal.

When requested, the composition readback reports `event_log_enabled`, `closed`,
`file_evidence_generated` and `sealed`. A completed run with logging disabled has
`closed: true`, `file_evidence_generated: false` and `sealed: false`. Its return
code is a business outcome; it has no persisted evidence seal for qualification
or file-evidence acceptance. Enable logging for runs that require those records.
