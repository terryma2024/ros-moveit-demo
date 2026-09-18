# Independent design re-review audit

review_date: 2026-09-18
reviewer: GPT-6 Astra / High, independent reviewer
decision: PASS
reviewed_document: docs/superpowers/specs/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design.md
reviewed_document_lines: 576
reviewed_document_sha256: 5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b
prior_review: docs/superpowers/reviews/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design-review.md
prior_review_sha256: d65708d9cebaafaae5f61eb3b0806f9e4341f2762cd6f66c128bdbe1ba197ba3
design_source_snapshot: ai-station:/data/work/ws_moveit@147d64a199bdf9c9b360555e15ad6ae85804ac39
fresh_remote_head: 6701a7be794eac410aa351106cbc17d58568d1ad
registered_evidence_root: /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main

## Decision and limits

The complete 576-line revision was read, including the retained scope/compatibility sections and new control, accounting, clock, coverage, and identity contracts. F1-F4 and C1-C3 are closed at design level. No additional blocking design defect was found. PASS approves this design as input to implementation planning; it does not assert implemented behavior, test success, measured budgets, exact-N qualification, recovery deployment, or permission to launch services.

No author document or prior review was modified. No implementation, pytest, dst, ROS/Web launch, cleanup, deployment, commit, or push was performed. Read-only source/remote checks and this new audit record are the only task actions. Previously read AGENTS.md and so101-dev instructions/references remain applicable. The prior review remains the immutable record of the original findings.

## Closure assessment

| Finding | Revision evidence | Independent assessment |
| --- | --- | --- |
| F1: recursive qualification/configuration identity | 102-108, 434-488 | CLOSED. The closed config separates execution from exactly three deployment references. L/S/E/I/R are fixed before measurement; B and Q do not point back to P; P points to Q; M and A1/D provide independent approval and raw-byte deployment audit. Only the two declared source/installed config carriers use the semantic digest. Executable/wrapper/dependency byte changes still invalidate R. First promotion can change null references without recursive remeasurement. |
| F2: standalone candidate abort authority | 196-233, 539, 570-576 | CLOSED. MeasurementOwnerBinding supplies authenticated control without a production Web lease. The control predicate is explicitly connected to broker startup/warmup/reload, worker start/recovery, child wait, and finalization. Sampler progress and owner health are monitored separately; abort latches stop replacement and grants. ACK and physical cleanup are distinct, with owned containment and unresolved cleanup fenced. The design requires the matching no-Web and sampler-loss regressions. |
| F3: unmeasurable literal RTF threshold | 320-367 | CLOSED. q comes from the frozen effective pace; slot/generation/session/reset/publisher identity defines clock epochs. Eligible phases, complete non-overlapping windows, bounded exclusions, frozen timestamp/quantization uncertainty, deficit intervals, cumulative lag, and independent freshness/deadline checks are specified. A bounded CALIBRATION_ONLY phase supplies epsilon without needing qualification first, and cannot itself earn a pass. The former mechanical every-window >=1.0 rule is explicitly withdrawn. |
| F4: insufficient workload coverage | 371-420, 424-427 | CLOSED. Five normal runs are no longer sufficient on their own. The exact-N coverage matrix covers cold start, YOLO, Grounded/SAM, mixed inference/render, actual motion/release, broker reload with N resident, worker recovery with N-1 resident, and cleanup. Valid recovery/failure pressure peaks enter the resource envelope while fault outcomes remain outside normal/business qualification statistics. Missing phases stay NOT_COVERED even if all points have valid terminal failures. |
| C1: ambiguous purpose/context and adaptive bypass | 135-169 | CLOSED. Production, measurement, and adaptive contexts have separate authority constructors and closed identity checks. Measurement has no approved-profile parameter requirement; production cannot obtain its context through the Web path. The old generic false resource flag becomes a typed adaptive-only context, preserving adaptive authority without granting fixed-mode bypass. |
| C2: headroom units/accounting and in-flight double counting | 243-318 | CLOSED at design level. Bytes and core-equivalent units, restricted cpuset/ancestor quota, whole-host RAM/GPU values, separate PSS/cgroup views, baseline/tool accounting, conservative stage deltas, pre-spawn equations, in-flight remaining-increment equations, and exact-20% table fixtures are explicit. Unknown attribution, background drift, or stage transitions cannot be used to admit new resource work. |
| C3: wrong recovery ledger | 515-525 | CLOSED. The serving continuation ledger is now the recovery reference; its header is explicitly not treated as the latest state. Historical development evidence keeps its own root, and fresh runtime/root task-ledger evidence must resolve the final checkpoint. |

The pass relies on the explicit acyclic graph in section 8.1 as the normative identity contract: a profile's descriptive status/review references cannot substitute for independent M/D authority or introduce a future-parent digest back into P. The implementation plan should carry that rule into parser/type tests without weakening it.

## Fresh source and runtime drift

Read-only re-review found a newer remote HEAD than the document's dated observation. The intervening commit is `6701a7be7 feat(tools): retain guarded ai-station runtime process cleanup`. Its diff adds only:

- `scripts/runtime_cleanup/README.md`
- `scripts/runtime_cleanup/ai_station.py`
- `scripts/runtime_cleanup/tests/test_ai_station.py`

`git diff --quiet 147d64a199bdf9c9b360555e15ad6ae85804ac39 HEAD -- src/so101_demo_py src/so101_teleop third_party/mujoco_ros2_control` returned exit 0. Thus the actual fixed-resource, operator-recovery, adaptive, control, and simulator interfaces used in the review are unchanged by this new commit. Tracked remote source remained clean with the same two unrelated untracked documents. The new cleanup script was not run and is not a new implementation requirement or cleanup authorization.

Fresh checks still found neither `src/so101_teleop/so101_teleop/expert_validation/operator_recovery.py` nor `install/so101_teleop/lib/so101_teleop/so101_expert_validation_recover.py`. This rules out treating the new HEAD as publication of the six-file recovery snapshot. It does not replace later source/install/runtime provenance verification.

The prior service PID 1264438 and parent 461503 were absent, and pane %63 was no longer listed. A process scan did not find an expert-validation server/recovery process; the only text match was the read-only inspection shell itself. This observation does not establish who stopped the service, whether cleanup was verified, or that any ownership/domain/fence is free. Those questions remain for the authorized execution preflight.

### N1 [P2, non-blocking] Treat section 2 service/source facts as a dated observation

Design locations: lines 38-63; execution safeguards at 507-525.

The phrase that PID 1264438 is currently running is no longer a live fact. Minimum follow-up: retain the original dated snapshot and append the fresh HEAD/service observation to the implementation plan's starting checkpoint. Before any execution, inspect source, install, process/store/control identities and the serving/root ledgers again. Resolve whether a service remains to preserve or whether a separately authorized restart is needed; do not issue stop/recovery commands using the obsolete PID/pane. Do not declare the service healthy, cleanup complete, or recovery deployed from either commit label.

This does not block the architectural design: the affected source interfaces did not change, and section 9 already requires fresh ownership/deployment-window checks. If the design is later edited to update its status or snapshot, preserve this review's exact-hash binding as the review of this revision.

## Handoff

The next deliverable is a Sol / High implementation plan with independent Astra / High review. It should turn the accepted design's regression requirements into scoped tasks, explicit source/install boundaries, and ordered verification gates. Missing implementation is expected in this docs-only review and is not a new finding. All budgets remain NOT_MEASURED and no worker count receives production qualification here.

retained: this re-review, the unchanged first review, the reviewed design revision, and all existing evidence.
archived: none.
deletion_candidates_created_by_re_review: none.
