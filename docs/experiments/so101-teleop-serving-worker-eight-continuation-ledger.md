task_id: so101-teleop-serving-worker-eight-continuation
goal: Resume Kimi serving recovery and fixed-worker capability/dropdown 1..8 inline.
success_contract: RED/GREEN regressions; package/frontend/build/codegen/native Chrome readbacks; Tailscale 8000 only; qualification stays fail closed.
worktree: /data/work/ws_moveit
branch: main
base_commit: 9ce38e2c931b0435113c9c72a7c6753fa0d54a83
current_commit: 64c19bf77e8c2fd870bf61ecead1005dbf66a0a6
evidence_root: /data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main
latest_checkpoint: CP-C05
next_experiment: NONE

## CP-C01 — inherited state verified

- Source initially clean main at expected merge; submodule third_party/mujoco_ros2_control e4c0241aee52a40727681bd5872c09bf814e941a.
- Historical EXP-K03 / acceptance-summary read completely. R05 conditional N/A, no live retry executed. Historical ledger and worktree remain read-only.
- Receipt exclusively created/read back, exact bytes CODEX-KIMI-CONTINUE-20260917-9CE38E2C, no newline.
- Existing owned serving candidate PID 482586 started 2026-09-17 16:35:06, parent 461503, so101-expert-validation pane %63. Only bind 100.82.102.56:8000; no 8001. Restart requires fresh identity and no active campaign.
- Preserved: existing so101-mujoco stack, all unrelated codex windows, Kimi session, independent dst task. No subagents.
- Runtime python: /data/work/so101-evidence/teleop-chrome-e2e/20260916T130435Z-e2ffff62-kimi01/python-venv/bin/python3; install overlay /data/work/ws_moveit/install; ROS_DOMAIN_ID 179; GZ_PARTITION not applicable (web-only).
- Previously blank page recovered with explicit source dist serving. Strict copied-install provenance has not been qualified by that recovery.
- No disproven continuation route yet; source API/preflight/upstream frozen config all cap fixed workers at 3.

## EXP-C01 — PLANNED

prior_experiment: EXP-K03 (historical completed E2E, reference only)
hypothesis: UI and API/preflight hard limits plus upstream frozen capacity/domain policy prevent exact N8 requests; symlink asset containment separately explains install asset 404.
prediction: capability/UI/API and upstream N8 regressions fail at their intended boundaries before modifications.
single_variable: requested fixed worker range
lifecycle: REUSE_STACK
preconditions: clean canonical main; read-only live service; no competing robot stack launched
success_criteria: intended new regressions fail, then pass after scoped changes; retain count and qualification gates
invalid_criteria: test collection/bootstrap failure
provenance: source 9ce38e2c931b0435113c9c72a7c6753fa0d54a83; install /data/work/ws_moveit/install; runtime venv above; ROS_DOMAIN_ID 179; GZ_PARTITION not applicable
retained: sole evidence root above; historical evidence roots are references only
archived: none
deletion_candidates: new scratch trees after test readback; no deletion authorized

## EXP-C01 results / CP-C02

- RED: r2 JUnit 10 assertion failures/5 passes at intended old limits and asset boundary; r3 qualification regression failed on admission true. Frontend RED 2 failures on hardcoded options.
- r1 sandbox ASGI client stalled; own pytest PID 531092 terminated after process inspection. INVALID environment run, not RED.
- g1 exposed stale copied so101_demo installed modules while source config had changed; bootstrap/provenance failures retained, not treated as source regressions. Rebuilt existing complete dependency overlay with colcon build --packages-select so101_demo_py so101_teleop --symlink-install; exit 0, 2 packages.
- GREEN g2: 16 passed; full Teleop t1: 489 passed, 40 s; upstream affected d1: 430 passed, 10 s. Frontend 112 passed, build exit 0. Bun 1.3.14 regenerated validation OpenAPI and TS.
- Ordinary demo full gate d2 failed collection on missing torch in exact Kimi venv, zero product assertions; retained as environment blocker, no dependency install. Benchmark suite not collected.
- Chrome setup first: 7 pass, C07 INVALID because this task rebuilt dist while fixture checked it; N8 option visibly had disabled attribute but Playwright toBeDisabled does not recognize option. Corrected to DOM disabled property; stable-dist second gate planned, separately retained output.
- Upstream closed request/config capacity now 8 and domains 181..188; thresholds unchanged. Counts4..8 reject FIXED_WORKER_LIVE_QUALIFICATION_REQUIRED in host admission, fixed CLI and fixed allocator. Existing adaptive ownership, separate domain policy and observations untouched. No fixed8 execution/qualification claimed.
- Symlink installed assets fixed at absolute /assets route; copied install identity checks unchanged. serve.sh now points to installed web directory; still symlink-install provenance.

## EXP-C02 — PLANNED

prior_experiment: EXP-C01
hypothesis: Fresh scoped overlay and symlink-aware assets resolve the original blank page and expose count1..8 on Tailscale8000.
single_variable: exact dedicated service revision/config
lifecycle: REUSE_STACK (preserve robot stack; restart dedicated web service only)
preconditions: fresh PID/start/pane identity; no active campaign and no owner; exact executables test -x
success_criteria: only100.82.102.56:8000; native GoogleChrome Campaign setup rendered; asset hashes source/install/HTTP identical; N8/K3 capacity24/20 and rejected exact request; N2/K10 capacity20/20
invalid_criteria: active campaign, stale/ambiguous ownership, build race
provenance: main source working diff at9ce38e2c; existing complete /data/work/ws_moveit/install; Kimi venv executable; ROS_DOMAIN_ID179; GZ_PARTITION not_applicable
owned_processes: existing expert-validation service PID482586 in %63 eligible only after fresh gates; no robot child resources
next_command: python3 continuation-restart.py

## EXP-C02 runtime results / CP-C03

- First web restart exited before startup with ModuleNotFoundError so101_demo after this task selected symlink-install for Python package. INVALID bootstrap run. Restored original normal copy-install via colcon build --packages-select so101_demo_py (exit0,1package); retained both logs. No module/config symlink identity check relaxed.
- Current dedicated service PID548153, parent461503, pane%63, started2026-09-17 17:15:24. Health200, fixed_worker_counts=[1,2,3,4,5,6,7,8]; only100.82.102.56:8000. No8001. Regular tasks remain503 VALIDATION_TASKS_DISABLED.
- Native GoogleChrome readback PASS on real URL; no page/console errors, exact PARALLEL N8/K3 request and response configuration preserved, capacity24/20. DefaultPARALLELN2/K10 at20points capacity20/20 verified before N8.
- Actual N8 preflight HTTP200 admitted=false with FIXED_WORKER_LIVE_QUALIFICATION_REQUIRED, CPU_HEADROOM, RAM_HEADROOM. Observations CPU24, availableRAM22.762GiB, GPUfree13.383GiB; requirements CPU32/RAM38GiB/GPU8GiB. No count-schema upper-bound error and no silent reduction. No campaign spawned.
- Native capture through healthy cua-driver0.19.3, strict window session, ChromePID550505/window52428804. Visually inspected native-window.png at its original generated resolution1568x1301: fullCampaign setup, worker8, K3, Capacity24/20 and20-point map visible. Screenshot notice had advanced to lease-renewed; rejected-admission fact comes from exact HTTP evidence, not screenshot. Session ended; browser closed its own context and lease release200; campaigns empty.
- Source/install/HTTP HTML/JS/CSS bytes match exactly; hashes in checks/source-install-http-manifest.json. Installed web uses symlink chain; this is explicitly not strict copied-install acceptance. Backend source/copied install hashes match too.
- Codegen repeated through Bun, both OpenAPI/TS SHA256 checks unchanged. Frontendbuild exit0; known large-bundle warning retained.
- Second Chrome setup8pass/1test-side failure: unavailable-mode request rejected before fixture command log, so preflight log row correctly absent. Changed new N8 regression to assert actual HTTP request/response, not nonexistent accepted-command log. Third fullsetup gate running, separately retained.
- Found existing Torch-capable venv at moveit-expert-validation-web/20260916-e1701375-a01/python-venv; verified torch2.13.0+cu130/pytest7.4.4/pydantic2.13.4 and canonical install imports. Full ordinary demo suite d3 running with newNVMe scratch; no install and no benchmark collection.
- Review remains inline under user instruction; no subagents. Independent dst task unchanged/unmessaged; historical Kimi ledger/reports unchanged. Shared MuJoCo stack preserved.
- Retained all continuation checks/runs under sole registered root. Archivednone. Deletioncandidates: scratch/* after readback and task-owned /tmp/so101-debug-kimi-continuation-chrome; no evidence deleted.

## CP-C04 — implementation and inline review complete

- Root causes: canonical /assets did not follow installed asset symlink chains; fixed worker constraints independently capped UI, API, preflight and frozen upstream config at3.
- UI now renders server capability counts1..8; PARALLEL1 is visibly SEQUENTIAL-only and disabled. SEQUENTIAL1 and ADAPTIVE ladder/ownership are preserved; requested fixedN is never reduced.
- Fixed request capacity supports1..8 with domain IDs181..188. Host admission, fixed CLI and fixed allocator explicitly reject4..8 with FIXED_WORKER_LIVE_QUALIFICATION_REQUIRED. No domain claims or campaign execution occurred forN8.
- RED r2/r3 and frontend regressions reached intended boundaries. GREEN g2=16; fullTeleop t1=489; affectedupstream d1=430; fixtureloader p1=12. Frontend112/28files; TypeScript/Vitebuild0; repeated Bun codegen produced identical JSON/TS hashes.
- Ordinary demo full d3:3142passed,1skipped,1failed,4warnings,637.71s pytest time. Failure is existing shared-install gazebo_ready, modified2026-08-29, absent from baseline setup registration. d4 reproduces it. Preserved shared artifact; fresh package install built against complete canonical underlay, d5 same test1passed. Full shared-install gate is not labeledPASS; strict copied-install qualification remains unclaimed. No benchmark collection or dependency install.
- Chrome setup thirdfullgate:8existing casespassed; newN8 case failed only because expected409 console diagnostic was not allowed. Fourthgate reran newN8 alone andpassed1/1, filtering only the exact expected409 diagnostic. Thus all9 scoped setup cases have passing evidence across retained runs; no claim of a single9/9run. Real native Chrome on Tailscale alsoPASS, exact8/K3 request rejected without count reduction, screenshot visually inspected.
- Inline review checked API boundaries, resource-before-domain behavior, asset/SPA/artifact separation, generated schema, native network payload and all remaining count3 logic. Remaining count3 branches are preserved qualification gates, not schema caps. git diff --check clean.
- Beforecommit:9ce38e2c931b0435113c9c72a7c6753fa0d54a83 plus exclusively task-owned scoped diff. Scoped local commit permitted; exact final revision and dedicated-service readback will be recorded in registered-root task-ledger.md and completion-report.md. No remote operations.
- Retained: all successful, failed and INVALID continuation runs/checks plus fresh-demo build/install under sole registered root. Archived:none. Deletioncandidates after readback:scratch/* and task-owned /tmp/so101-debug-kimi-continuation-chrome. No deletion.

## EXP-C03 — PLANNED final revision readback

prior_experiment: EXP-C02
single_variable: immutable local source revision
lifecycle: REUSE_STACK
preconditions: fresh servicePID548153/starttime/pane%63 match; campaigns empty, no ACTIVE lease and no owned_execution; exact executable paths verified
success_criteria: health200; only100.82.102.56:8000; counts1..8; generated manifest source_commit equals committedHEAD; source/install/HTTP hashes identical; exactN2K10capacity20 andN8K3capacity24 with qualification rejection; own lease released
invalid_criteria: stale ownership or any active lease/campaign; do not interrupt those
next_command: commit scoped source then final-continuation-restart.py and final-runtime-readback.py

## CP-C05 — canonical committed serving verified

- Verified implementation commit64c19bf77e8c2fd870bf61ecead1005dbf66a0a6, before9ce38e2c931b0435113c9c72a7c6753fa0d54a83; local commit only,19paths. Final ledger-only commit/rebound service receipt will be recorded in registered root.
- Final revision assertion caught inherited SO101_VALIDATION_PROVENANCE_BINDING pointing to historical kimi-overlay-binding.json/worktree9d5da0bb. This explained prior startup succeeding while canonical source was dirty. Preserved historical binding; owned serve.sh now unsets inherited validation/parallel bindings, requires SO101_VALIDATION_SOURCE_ROOT canonicalWS and SOURCE_COMMIT actual GitHEAD. Strict clean-Git/module/config identity checks unchanged.
- Guarded web-only restart validated exact process/start/pane plus empty campaigns, no ACTIVE leases and no owned_execution. Final source manifest reports canonical committed64c19bf77, not historicalKimi. Earlier failed final assertion and inherited env evidence retained; no campaign was started.
- Verification script initially assumed capacity wire field; published PreflightResponse intentionally exposes execution_config. Corrected audit script to compute capacity from exact returnedN*K and compare20-point count, retained prior script version. Final readback exit0: N2K10capacity20 admittedtrue/reasons[]; N8K3capacity24 admittedfalse/reasons[FIXED_WORKER_LIVE_QUALIFICATION_REQUIRED,CPU_HEADROOM,RAM_HEADROOM]. Own lease release200; campaigns empty.
- Final source/install/HTTP assets and backend bytes rechecked unchanged. Real served URL http://100.82.102.56:8000/expert-validation. OnlyTailscale8000; regulartasks503; missingasset/artifact404. Frontend native image remains applicable because code/builded assets unchanged after native inspection.
- Full ordinarydemo d3 final process exit1, JUnit3144tests/1failure/0errors/1skip;3142passes; elapsed640s. Sole failure classified shared-install contamination with d5fresh-installPASS. This limitation and fixed4..8 live qualification remain explicit; strict copied-install acceptance notPASS.
- Requested blank-page and1..8dropdown work complete; no fixed8 live execution claim. Independent dst task unmodified/unmessaged; no subagents, push, evidence deletion, dependency installation, hardware use or shared robot restart.
- Retained all continuation evidence at registered root; archivednone. Deletioncandidates scratch/* and owned short browser temp directory; no deletion authorized or performed.
