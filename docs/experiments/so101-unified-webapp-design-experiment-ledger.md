# Unified Web App design ledger

```yaml
task_id: so101-unified-webapp-design-20260918
goal: Design and plan one Teleop and expert-validation Web service with shadcn preset b311momZs0
success_contract: User-approved written design and independently reviewed implementation plan before execution
worktree: /Users/matianyi/.codex/worktrees/587b/moveit-demo
branch: codex/teleop-adaptive-worker-pool-docs
base_commit: 303c2cb9e2b1faea55a6d82dac2197da7512be96
current_commit: 6afd834f02ea537dcad8d65e282a8491f6c6e830
source_inspection_worktree: /private/tmp/so101-doc-publication.R3yXD0aj/repo
source_inspection_commit: 84620fc0529779a27c6985f8717d78f0386e0135
evidence_root: /tmp/so101-debug-unified-webapp-design-20260918
confirmed_conclusions:
  - Design-only authorization; no implementation or runtime changes
  - Resource-budget implementation remains independently owned by dst-unbounded-queue on ai-station
  - User approved one HTTP/WebSocket service with non-Web ROS worker and executor subprocesses
  - User approved single-Web plus non-Web ROS subprocess architecture and default global mutation exclusion during validation
  - User approved the v2 interactive two-page layout direction
  - User approved final state, migration and acceptance section; all discussion sections approved
  - Independent Astra/High rereview passed the corrected exact-hash static design
  - User approved the written spec and authorized implementation-plan writing; implementation remains unauthorized
  - Independent Astra/High final review passed the corrected exact-hash static implementation plan
disproven_routes: []
open_hypotheses:
  - Consolidate two application lifecycles into one Web process while preserving runtime ownership boundaries
latest_checkpoint: CP-20
next_experiment: NONE
```

## CP-01: Context and inspection boundary

Original local worktree remains on its older docs branch with existing model-policy and frozen budget documents, and preserved untracked recovery guide/proposal. Read current published main from the retained publication worktree using its explicit Git directory. Do not rebase or modify either runtime source tree while the dst task proceeds.

ai-station canonical main remains at 6701a7be794eac410aa351106cbc17d58568d1ad; origin/main published 84620fc0529779a27c6985f8717d78f0386e0135. Registered dst implementation worktree is on the latter base. Preserved tmux panes: codex %0, codex %60, dst-unbounded-queue %68. No Web/robot runtime launched for this design task. No ROS live-state or browser acceptance asserted.

Bun executable /Users/matianyi/.bun/bin/bun, version 1.3.14. Existing frontend package uses React 18, Vite 5, Tailwind 3.4.17, Bun lock, shadcn new-york/neutral/lucide configuration. Incoming preset must be inspected through the official CLI, not hand decoded or applied during design.

Design author: GPT-5.6 Sol / High. Root inspects preset metadata and coordinates the discussion. No written spec or implementation plan yet; architecture and remaining questions require user approval first.

Retained: inspection logs under the registered evidence root. Archived: none. Deletion candidates: none. No evidence deleted.

## CP-02: Preset and initial architecture verified

Official Bun-run shadcn CLI decoded b311momZs0: version b, maia, mist base/chart, blue theme, lucide icons, dm-sans body font, outfit headings, large radius, subtle menu accent, default menu color. Generated preset URL: https://ui.shadcn.com/create?preset=b311momZs0. No apply/init/add was run. Initial CLI failed due to tempdir write permission; retry used task-root TMPDIR and a task-local Bun cache and succeeded. Logs: preset-decode.txt, preset-decode-retry.txt, shadcn-info.json, component-doc-urls.txt under the registered root.

CLI info reports Tailwind v4, but source package declares 3.4.17 and index.css uses v3 directives; design must resolve compatibility explicitly rather than accepting this detector output. Official Sidebar, Resizable, Card, Field and AlertDialog documentation inspected; no components were installed into the repository.

Current main frontend already uses one Vite entry/bundle, with pathname selection of Teleop, Tasks and ExpertValidation roots (main.tsx lines 10–14). Sol read-only inspection finds separate HTTP compositions and cleanup owners. Proposed consolidation is one FastAPI/uvicorn service with unified static/router/lifespan and independent domain capability readiness, preserving ROS/executor subprocesses and worker ownership.

Source inspection worktree remains clean. No runtime, code, budget-task or historical evidence changes. Next step: user clarification of cross-feature runtime concurrency versus mutually exclusive mutation policy; then sectioned design approval. No implementation approval inferred.

Retained: registered CLI evidence and cache. Archived: none. Deletion candidates: task-local disposable Bun cache (not deleted). Owned robot processes: none. Preserved: existing codex and dst sessions. Next command: NONE pending discussion.

## CP-03: Single Web-service boundary approved

User response `ok` confirms one HTTP/WebSocket service, allowing ROS workers and sampling executors as non-Web subprocesses. It does not approve implementation or the remaining detailed design.

Sol/High is preparing the first architecture/lifecycle section and the cross-feature mutation policy choice. Current legacy task facade already blocks Teleop writes while its bound task runtime is active; unified-service design must extend server-side arbitration to validation ownership without reusing domain lease tokens. No service, source implementation, preset installation or dst-task changes.

Retained evidence remains in the one registered root. Archived: none. Deletion candidates unchanged. Next command: NONE pending design discussion.

## CP-04: Architecture and exclusion approved; UI discussion next

User response `ok` approves the presented first architecture section and default global mutual exclusion: validation execution keeps Teleop readable while rejecting motion, execute and reset, with validation cancellation retaining its original safety path. This remains design approval, not implementation authorization.

Sol/High prepared a candidate second section: unified Sidebar with Teleop and Expert Validation primary entries, existing /tasks compatibility, domain-specific state, Teleop adjustable panels preserving current controls, Validation configuration strip plus equal-scale top-view and multicolumn results with evidence Sheet. Preset-driven components/tokens use smart merge preserving business behavior. These UI details are not yet user approved.

The next layout discussion benefits from visual presentation. Offer brainstorming visual companion in a standalone message and wait for approval before creating or opening mockups. No mockup server, UI implementation, service or dst-task change has been made.

Retained/archived/deletion classifications unchanged; no evidence deleted. Next command: NONE pending visual-companion preference.

## CP-05: Visual companion authorized and started

User requested `看草图`, authorizing a local interactive layout mockup and browser presentation, not production implementation. Read the brainstorming visual-companion guide completely and use its supplied server with `--open --foreground`. Project directory points to this task's evidence root so all generated mockup/state/log artifacts stay outside source and within the one registered root.

Preview server session: /tmp/so101-debug-unified-webapp-design-20260918/.superpowers/brainstorm/59690-1789699029. Listen address 127.0.0.1, port 64578, four-hour idle timeout. Tool-owned process session 56442. Preserve the complete keyed URL from state/server-info when presenting the preview; key is local session access control, not a robot credential. Server launch was explicitly approved; no remote services or task sessions changed.

Sol/High authors one disposable HTML/SVG sketch for both pages. It uses example-only statuses and coordinates, not real campaign evidence or runtime budgets. No API connection, mechanical action, production shadcn installation, spec or implementation plan. Main checks rendering and local navigation/evidence interactions through the in-app browser before handoff.

Retained: companion session, mockup and task-local inspection evidence. Archived: none. Deletion candidates: cache and provisional mockup/server session after user design decision (no deletion authorized).

## CP-06: Interactive sketch presented and visually checked

Sol/High authored v1, retained SHA256 7fc00115bae6c4d8f48500ede11b2b27abfc440a39f12b3bf4a6c8544ce2c4bb. Main created the serving copy with apply_patch. Browser inspection found the sketch represented six arm joints plus gripper; Sol verified actual source uses arm IDs 1..5 and gripper ID 6, then created a one-line v2 correction without overwriting v1. v2 SHA256 c075978d6db51d4cd7e23ff94b28ab47370be562c2ee7cb09dec84a298727dbf, serving filename content/unified-webapp-layout-v2.html. Both roots and serving copies remain inside the registered evidence root.

Browser checks: desktop 1400x900 has no horizontal overflow, left/right grid columns 678/452 pixels, map stage 676 pixels wide, three result columns and twenty SVG point circles all r=18. Clicked P15 result and confirmed named P15 evidence dialog/aria-hidden=false, then closed it and confirmed aria-hidden=true. Navigated Teleop and inspected readonly reason and disabled motion/reset controls; final v2 has six sliders labeled J1..J5 and gripper. Theme toggle changed actual body background/class, then returned to light. On 390x844 mobile viewport, document scroll width equals 390 and results use two columns; menu opens, navigation changes page, menu closes. Temporary viewport overrides reset before user handoff; preview tab marked deliverable.

Fresh desktop screenshots: validation-desktop-v2.png and teleop-desktop-v2.png. Retained additional evidence-sheet-v1.png and mobile-validation-stable-v1.png. Initial full-page screenshot showed capture stitching artifacts from fixed/sticky elements; it is not layout acceptance evidence. A first mobile screenshot occurred during menu CSS transition; stable readback confirmed sidebar fully offscreen at x=-228 and stable screenshot is the retained visual check. No product code or safeguards were changed to compensate for capture behavior.

Sketch is pure HTML/SVG with example coordinates/status, approximate preset treatment and font fallbacks, not installed production shadcn components. Main and Sol performed no robot action, API connection, dependency installation into source or ai-station task changes. This checkpoint proves sketch presentation/local interactions only, not Web app implementation, qualification or production acceptance.

Next step: user layout feedback before advancing design sections or writing the approved spec. Retained: v1/v2 originals, serving copies, screenshots, companion session and CLI evidence. Archived: none. Deletion candidates: task-local CLI cache and superseded provisional/capture artifacts; none deleted.

## CP-07: Layout approved; final behavior and acceptance section proposed

User response `ok的` approves the presented v2 layout direction. It does not claim the approximate HTML sketch is a production shadcn implementation or grant implementation authorization. Sol/High supplied the final proposed section covering unified route aggregation, root-level domain-specific subscriptions/heartbeat, sequence/generation reconnect without command replay, symmetric server-side mutation arbitration, unknown-owner/recovery/cleanup fail-closed states, Teleop IPC fault isolation, journal readback without auto takeover, preset smart merge and compatibility/toolchain gates, Chrome/accessibility/regression acceptance, and fresh runtime qualification after R changes.

These final behavioral details require section approval before writing the complete spec. No formal design, implementation plan, production code, service or dst-task changes. Companion server fresh check: state/server-info exists and state/server-stopped absent; no browser-choice events were present. Pushed a new waiting-unified-design-v1.html screen, retaining both mockup versions and screenshots, while discussion returns to chat.

Next step: final section approval, then Sol/High formal spec followed by independent Astra/High review. Retained/archived/deletion classifications unchanged; nothing deleted. Next command: NONE pending design approval.

## CP-08: All design sections approved; formal spec drafting

User response `ok` approves the final behavior, migration and acceptance section. All discussed sections are approved for formal design writing. This does not authorize implementation, deployment, live robot tests or changes to the independently running dst task.

Sol/High is drafting docs/superpowers/specs/2026-09-18-so101-unified-webapp-shadcn-design.md with humanizer-zh and the verified current-main source baseline. Root verifies documentation scope and then requests an independent Astra/High review of the exact written artifact. Do not write an implementation plan until the user reviews the written spec.

Retained: registered inspection, preset, sketch and browser evidence. Archived: none. Deletion candidates: task-local CLI cache and provisional sketch/capture artifacts; none deleted. No runtime process owned or changed by this design task. Next experiment: NONE.

## CP-09: Formal spec frozen and independent review started

Sol/High wrote and self-reviewed the formal spec, SHA256 f986ff881ef6e34f0c8fcd44e1444bb91dc8ff0f957863f5334bc66118111548, 233 lines. Root read the complete artifact and independently read back its hash. Source references use the published 84620 baseline. Relative budget links resolve, code fences close and whitespace checks emitted no diagnostics. No product tests were run; these are documentation checks only.

Budget spec remains SHA256 5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b and budget plan remains cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bfc8789. No frozen budget changes or ai-station operation.

Independent reviewer: GPT-6 Astra / High, task astra_unified_webapp_design_review. Review is bound to the exact frozen spec hash; no author edits while review is active. Expected persistent report: docs/superpowers/reviews/2026-09-18-so101-unified-webapp-shadcn-design-review.md. The reviewer can read current publication source but cannot implement, execute tests or change the spec/ledger.

Retained: formal spec, registered design-review-checklist.md and prior task evidence. Archived: none. Deletion candidates unchanged; nothing deleted. Next experiment: NONE. Written-spec user review still required before implementation planning.

## CP-10: Independent review requires three design corrections

Astra/High first review: CHANGES_REQUIRED, report SHA256 bbe2a1962a77c00f9105cbc413601afb2903c545899e4275e06b082559dab8a8. Root read the entire report and verified its hash. R1/P1: Execute All requires a durable parent reservation across arm and gripper steps. R2/P1: cancellation must bypass ordinary command locks/IPC backlog and target exact arm/gripper action identities. R3/P2: server-verified controller-instance binding must define document refresh, route switches, reconnect and explicit handoff.

Root checked baseline client.ts:25 (separate arm/gripper POSTs), server.py:728/:858 and control.py:55 (cancel shares busy command lock), server.py:537 (arm-only latest goal cancel), and lease/session restoration checks. These are existing-source facts, not live fault reproduction. Read receiving-code-review before requesting changes. Sol/High is revising only the spec and acceptance contracts; preserve the first review report unchanged. No product correction or runtime success claimed.

Next: freeze a new spec hash, independent Astra/High rereview, then written-spec user review. Retained: first report and previous evidence. Archived: none. Deletion candidates unchanged; no evidence deleted. No ai-station operation. Next experiment: NONE.

## CP-11: Corrections frozen; independent rereview

Sol/High revised the spec to 275 lines, SHA256 4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1. Root read back the hash and reviewed all changed contracts. R1 maps to section 6.1, R2 to section 7.1 and R3 to section 5.1, with explicit fault/competition acceptance cuts in section 11. First-review report remains unchanged.

Astra/High is independently reviewing this new exact artifact, including regressions introduced by the corrections. New report path: docs/superpowers/reviews/2026-09-18-so101-unified-webapp-shadcn-design-rereview.md. No spec edits during review. Local scoped documentation commit follows only after verified review completion; no remote push or implementation inferred.

Retained: corrected spec, immutable first review and prior task evidence. Archived: none. Deletion candidates unchanged; nothing deleted. No runtime/test or ai-station task operation. Written-spec user approval still required before planning. Next experiment: NONE.

## CP-12: Static design PASS; scoped local documentation handoff

Astra/High complete rereview: PASS for exact spec SHA256 4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1. Rereview SHA256 3cd84e786dd8116d1c08216ff455f2a8e08f3fca62379469c5904d1a46a2eb42. Root read the complete rereview and independently checked both hashes and the unchanged first-review hash. R1–R3 closed; no remaining design-level P1/P2 finding. Implementation details and fault-injection evidence remain future gates.

The brainstorming workflow calls for a local design commit. Stage only this ledger, unified spec and the two unified-design review reports. Preserve the preexisting AGENTS change, recovery guide, fixed-eight proposal and budget docs/reviews unstaged. Use verified explicit Git metadata; no rebase, merge or remote push. Final committed SHA and staged/commit readback are recorded in the task-root local-commit-readback.md receipt after the commit. This is not a main publication.

Only documentation and temporary design artifacts were produced. No product tests, ROS/Chrome product acceptance, runtime measurement, service changes, dst interruption or ai-station operation. The user must review the written spec before implementation planning; no plan was written this turn.

Retained runs: design inspection/CLI, v1/v2 sketches, sketch-only browser checks and static review records under the registered root. Archived runs: none. Deletion candidates: task-local CLI cache, provisional sketch server/state and superseded captures; no deletion performed or authorized. Persistent design/spec/review/ledger retained in the repository. Next experiment/command: NONE pending written-spec user approval.

## CP-13: Written spec approved; implementation planning

User response `ok` approves the written design after the exact-hash Astra/High PASS. Begin implementation-plan writing, not implementation or deployment. Trusted checkpoint is CP-12: design SHA256 4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1, local design commit 6afd834f02ea537dcad8d65e282a8491f6c6e830. No disproven implementation experiment or runtime qualification exists for this feature.

Sol/High drafts docs/superpowers/plans/2026-09-18-so101-unified-webapp-shadcn-implementation.md using writing-plans, humanizer-zh, shadcn and so101-dev. The main agent verifies source boundaries and static spec coverage; Astra/High independently reviews the frozen plan. Preserve all existing unrelated dirty/untracked files. Read current source only from the inspected publication baseline, not the older original worktree source. Fresh source/runtime provenance is an execution preflight gate, not a planning-time runtime claim.

Only local documentation work this turn. No remote process inventory, ROS graph, GUI operation or runtime start is needed or authorized for planning; those checks are explicit execution prerequisites. Debug-evidence and Python installation references are unrelated to this documentation-only turn; no diagnosis, package installation or product test. Parent/root rules, system map, ledger and acceptance references were read. The independently dispatched budget dst task is preserved and not inspected or changed.

One existing registered evidence root continues. Root is sole ledger writer. Retained: prior evidence and planning checks; archived: none; deletion candidates unchanged and not deleted. Next experiment/command: NONE until plan approval.

## CP-14: Implementation plan frozen; independent review started

Sol/High completed the 13-task implementation plan, 933 lines, SHA256 d1fe79740faafa3494bb1b91e9c2dd5271e6cc79c1f06506ff5da56afc08eab4. Root independently read back this hash. Approved design remains SHA256 4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1; frozen budget plan remains cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bfc8789.

Root read the initial full plan and checked revisions to task ordering, cross-store lease/controller fencing, normal renewal, exact goal cancellation, real UI types and installed composition. Explicit Git diff --check exited 0. The untracked-plan no-index --check emitted no whitespace diagnostics and exited 1 because the file differs from /dev/null; this is not a product test or a claimed test PASS. Final review will include a fresh complete readback of the frozen artifact.

Astra/High prepared by inspecting the approved design and actual publication-source boundaries, then received the frozen plan hash for full independent review. Expected new report: docs/superpowers/reviews/2026-09-18-so101-unified-webapp-shadcn-plan-review.md. Author must not edit while review is active. No source implementation, product tests, build, runtime qualification, remote operation, commit or push this turn.

Retained: frozen plan, planning-cli-readback.md, implementation-plan-review-checklist.md and all previous registered evidence. Archived: none. Deletion candidates unchanged; nothing deleted. Next experiment/command: NONE pending independent review and user implementation approval.

## CP-15: First plan review requires six corrections

Astra/High full independent review: CHANGES_REQUIRED, report SHA256 f5bf485c0ce65030c5c14fb80fd78f66f5407323391c0bf2a78430598b3654d9, bound to plan d1fe79740faafa3494bb1b91e9c2dd5271e6cc79c1f06506ff5da56afc08eab4. Root read the complete report and independently checked its hash. PR1/P1: cross-channel pending-child cancellation and actual submission need a defined linearization protocol. PR2/P1: identify the pure production Teleop implementation and place installed helper substitution below application/parent/admission/safety layers. PR3/P2: isolated normal_lock does not exercise production cancellation contention. PR4/P2: Task9 still imports Task10's future qualification view. PR5/P2: Tasks artifacts use open, not Validation resolve_opaque_id. PR6/P2: ai-station-specific NVMe policy must not apply to every Linux host.

Root checked actual source api.py:219 (Tasks artifacts.open) and expert_validation/api.py:474 (Validation resolve_opaque_id). These are static source facts, not fault reproduction. receiving-code-review was read completely. Sol/High is revising only the plan, with files/interfaces/staging/tests aligned; preserve the first report and approved design unchanged. Also clarify the complete installed dependency closure rather than treating a Teleop-only development overlay as the full copied install.

Root complete-read checks of the first frozen plan: 13 tasks, 933 lines, 60 code fences, no missing relative links and no TODO/TBD/FIXME literals. These checks do not override independent review findings or qualify execution. No product tests or ai-station operations. Next: new plan hash and full independent rereview. Retained: first report and prior task evidence; archived: none; deletion candidates unchanged, no deletions. Next experiment/command: NONE pending review and implementation approval.

## CP-16: Six corrections frozen; independent full plan rereview

Sol/High revised only the plan to 1100 lines, SHA256 471785ae65b0a183b026627c6b9fcf88cb12a76cae175abc4b36dcc77eb45e28. Root independently read back this hash and read the complete frozen artifact. The first plan-review report remains f5bf485c0ce65030c5c14fb80fd78f66f5407323391c0bf2a78430598b3654d9.

PR1 now specifies stable pending-child keys, durable revocation revisions, child-local tombstones/short submission transitions, independent two-channel barriers and an irreversible Web-death latch. PR2 defines the pure production Teleop implementation/shared composition and substitutes only the leaf ActionDriver in installed tests. PR3 separates the isolated lane unit from production coordinator/queue contention tests, creating the latter after the real factory exists in Task6. PR4 delivers backend view/schema in Task6 and frontend UNKNOWN view in Task7 before Task9. PR5 uses the real Tasks open/OpenedArtifact API and unchanged Validation resolver. PR6 uses a verified host-specific policy instead of an OS-wide NVMe rule. Files/staging and sixteen CTest registrations are aligned; copied install requires the complete source dependency closure.

Main-agent fresh static checks: thirteen tasks, 1100 lines, seventy-two closed code fences, no missing relative links and no TODO/TBD/FIXME literals. These are documentation checks only. Astra/High received the new exact hash for complete independent rereview of corrections and regressions. New report path: docs/superpowers/reviews/2026-09-18-so101-unified-webapp-shadcn-plan-rereview.md. No author edits while review is active; no implementation, product tests, remote operation, commit or push.

Retained: corrected plan, immutable first report and all registered evidence. Archived: none. Deletion candidates unchanged; nothing deleted. Next experiment/command: NONE pending rereview and user implementation approval.

## CP-17: Full plan rereview narrows remaining correction to one parameter chain

Astra/High full rereview: CHANGES_REQUIRED, report SHA256 f171db5ee0dcac6edb75b47a4619bfd296f4f7f7c7f4a09cdd56885cbd864935, bound to plan 471785ae65b0a183b026627c6b9fcf88cb12a76cae175abc4b36dcc77eb45e28. Root read the complete report. PR1 and PR3–PR6 are closed at the static-plan level; PR2's production/lower-level Teleop composition is specified, but PR2-R/P2 remains: the shared composition signature omits the existing Validation execution_port seam passed by the installed launcher.

Root checked baseline production.py:1209/1213/1235, which explicitly receives and forwards execution_port. Request the minimal explicit shared-composition parameter chain, production-default/no helper selection, preserved test-source Validation HelperExecutionPort and same-object/owned-process evidence assertions. Teleop still substitutes only its leaf ActionDriver. Do not replace a high-level application service or start actual simulation to make L2 pass. First review and rereview stay immutable; approved spec and budget documents unchanged.

Sol/High is revising only the plan; final independent review must bind the next exact hash. No implementation, product tests, remote operation, commit or push. Retained: both plan reports and prior evidence; archived: none; deletion candidates unchanged, no deletions. Next experiment/command: NONE pending final review and user approval.

## CP-18: Minimal composition correction frozen; final independent review

Sol/High completed the PR2-R-only plan revision, 1105 lines, SHA256 71648ebbce07388af016e125c6e168b80fd3752305d62e71b412f64fdb6ae039. Root read back the hash and read all changed passages. Shared composition now explicitly forwards validation_execution_port to the existing production factory; production fixes the default real port and provides no helper selector. Test-source composition preserves the exact existing Validation leaf port object, alongside Teleop's leaf ActionDriver, and verifies same-object/owned-argv evidence through real routes in source and copied install. Root checked the real factory signature at production.py:1209–1235.

Astra/High final independent review is bound to this new exact hash and complete-plan consistency. New report path: docs/superpowers/reviews/2026-09-18-so101-unified-webapp-shadcn-plan-final-review.md. Keep both previous plan reports immutable and approved design/budget documents unchanged. No author edits during review. No implementation, product tests, runtime operations, commit or push.

Retained: all three plan revisions' audit references and both existing reports under the registered planning task. Archived: none. Deletion candidates unchanged; nothing deleted. Next experiment/command: NONE pending final review and user approval.

## CP-19: Static implementation plan PASS; documentation handoff

Astra/High final independent review: PASS for plan SHA256 71648ebbce07388af016e125c6e168b80fd3752305d62e71b412f64fdb6ae039, 1105 lines/thirteen tasks. Final report SHA256 d5f0fd935636f0d032a325776e721c6a667d6074e4a3b65eeb9f641f615e0eae. Root read the full report and independently verified the plan/report hashes. PR1–PR6 and PR2-R closed in the static plan, with no remaining plan-level blocking finding. First review f5bf485c0ce65030c5c14fb80fd78f66f5407323391c0bf2a78430598b3654d9 and rereview f171db5ee0dcac6edb75b47a4619bfd296f4f7f7c7f4a09cdd56885cbd864935 remain unchanged.

Approved unified design remains 4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1. Frozen budget spec remains 5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b and budget plan remains cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bfc8789. Preserve unrelated AGENTS/recovery-guide/fixed-eight-proposal/budget files and all remote tasks. No staging, commit or push this planning turn.

User implementation approval is still required. Fixed future executor is dst TUI/tmux inline in a new independently registered worktree/task; do not offer or silently substitute Codex subagent implementation. Final upstream budget interface, registry/compiler/dependency lock, actual ROS UUID support and all RED/GREEN/install/runtime qualification gates remain future checks. Static PASS does not authorize measuring/promoting a new profile, replacing existing services, live/hardware execution or deleting evidence.

Only local plan, three immutable independent plan reports, ledger checkpoints and temporary planning audit records were produced. No product tests, code edits, ROS/Chrome acceptance, service changes, ai-station operation or remote-budget-task inspection. Retained runs: all design/planning inspection, CLI, sketch-only captures and review evidence under the registered root, plus persistent repository docs. Archived runs: none. Deletion candidates: task-local CLI cache/provisional sketches/server state and superseded captures; no deletion authorized or performed. Final static check/readback receipt: planning-final-readback.md under the registered root. Next experiment/command: NONE pending user review/approval.

## CP-20: User authorizes scoped main publication

User request: merge to main, then push. This authorizes Git integration/publication of the reviewed unified-Web design/plan and their audit records, not code implementation, dst dispatch, service changes, qualification or evidence deletion. Last trusted checkpoint: CP-19 exact-hash static plan PASS; there are no disproven runtime experiments to repeat.

Fresh fetch of origin and github succeeded. Both main refs are 84620fc0529779a27c6985f8717d78f0386e0135 with divergence 0/0. Local main 4a5f83fd330aa72d0283539b911af44aacf6d515 has three unrelated unpublished W8/ACT documentation commits; keep them and their checkout unchanged, do not silently publish them. Original docs branch has older source/history and preserved dirty/untracked AGENTS, recovery guide, fixed-eight proposal and budget files.

Publish only eight unified task files: approved design, two design reports, implementation plan, three plan reports and this ledger. First scoped-commit the plan/reports/ledger on the original documentation branch, then transplant only local design commit 6afd834f and that new scoped commit onto fresh remote main in the existing clean publication worktree /private/tmp/so101-doc-publication.R3yXD0aj/repo. Keep prior publication branch intact; use a new codex/so101-unified-webapp-doc-publication-20260918 branch. Do not merge the old source tree or unrelated unpublished branches. Use explicit Git metadata for both linked worktrees; no reset/clean/force/gh.

Recheck fresh refs before ordinary fast-forward pushes to origin/main and github/main; if they move, preserve intervening commits and revalidate. Exact published commit, SHA/ancestry readbacks and clean publication status are recorded after push in main-publication-readback.md under the one registered evidence root. Only documentation static gates apply; no product tests, build, ROS/GUI/remote-runtime operation or agent dispatch. Retained: all prior evidence and publication receipts; archived: none; deletion candidates unchanged, nothing deleted. Next runtime experiment: NONE.
