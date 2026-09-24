# SO-101 ACT Parallel Collection Design Review Ledger

## Task identity

- Date: 2026-09-16
- Scope: Update the dual-RGB ACT design and implementation plan to use the merged adaptive multi-stack worker pool for MoveIt demonstration collection.
- Repository: `/Users/matianyi/Projects/robot_demo_001/moveit-demo`
- Starting HEAD: `e6c91cb6437f254f65531346bffaec53655e9162`
- Adaptive worker pool merge: `25d1130a990f34334b20e9ced4bcde4f4ed83aba`
- Registered evidence root: `/tmp/so101-debug-act-parallel-plan-review-9KjN50tq`

## Files under review

- `docs/superpowers/specs/2026-09-10-so101-act-head-wrist-rgb-design.md`
- `docs/superpowers/plans/2026-09-11-so101-act-head-wrist-rgb-implementation.md`

## Evidence boundary

This task changes documentation only. It does not implement the ACT collection workload and does not run MuJoCo, ROS, MoveIt, recording, training, or robot acceptance. Static checks and independent Astra review are valid evidence for document consistency only.

## Review log

| Round | Reviewer | Input hash | Result | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Astra high | Design `17d77b79bded3a01aa5b96a56ca4d99cd7503285b24eca30eee78fc75d1933b7`; plan `663c29b6aa80a0c7cf50fcc0770a66b18b09a7f68a054496075cd509c488c899` | Not passed: 2 P1, 4 P2 | Search was placed in the infrastructure gate; production child factories and result discovery were unspecified; socket paths were too long; quota selection depended on completion order; qualification mode was inconsistent; 8 scenarios did not qualify sustained W8 recording. |
| 2 | Astra high | Design `bca246c0...7707c7`; plan `dfdef9aa...8e1a7e3` | Not passed: 1 P1, 1 P2 | A crashed in-flight wave had no fence/reconcile/continuation protocol; the five-split manifest was passed to a three-split collection whitelist. P3 requested precise wording for stealable preferred assignments. |
| 3 | Astra high | Design `05ed06198bf43c4cf3a8c4f041bd08e536336d2f5ef2034a3cd9170041431646`; plan `4dff1e18664a8950748608be8ad6f8af6089b7e9e377ec2e1dd72777f99c5acc` | Not passed: 3 P2, 2 P3 | Reconcile could import a late seal after durable lease expiry; qualification did not require a pure worker level with zero retry/fallback/continuation; socket preflight omitted the command broker endpoint. The runbook lacked a full eight-scene single-stack command, and Task 14 repeated a Create marker. |
| 4 | Astra high | Design `73db08a54f9a29aa5b4c164a214fbc824b981250bb69ee0fb42fd3c4de264b67`; plan `18c83ec26203c6ee08a3afe61d3807f4cc47eea3b34fba14460fb36053fb022e` | PASS: no P0/P1/P2 | One non-blocking P3 requested a constructible socket test: endpoint membership and shared consumers plus the full-list 107/108-byte boundary. The wording was updated after review. |
| 5 | Astra high | Design `73db08a54f9a29aa5b4c164a214fbc824b981250bb69ee0fb42fd3c4de264b67`; plan `6a7985f6a3ffc3c25eeb02722899ae6e9c4f4bccb727a52bc9137287c163e93a` | PASS: no P0/P1/P2/P3 | Final hash-lock readback confirmed the shared socket endpoint manifest, 107/108-byte boundary, and unchanged implementation contracts. |

## Evidence disposition

- Retained: this ledger and the two reviewed documents.
- Archived: none.
- Deletion candidates: `/tmp/so101-debug-act-parallel-plan-review-9KjN50tq` after final readback; do not delete without explicit authorization.

## 2026-09-24 main-contract refresh

### Task identity

- Scope: Reconcile the reviewed ACT collection and training design with the later `main` contracts, independently review the documents, and recover/rebase the last available ACT implementation branch without starting implementation, data collection, or training.
- Local source HEAD: `b238eca2d6d280989a6f71529e53a91b29aa301b`.
- Compared ai-station `main`: `fd7348aa27361750f7e2e7954df53ef75e96545c`.
- Last recoverable ACT branch commit before rebase: `e2ec28c33ecaa455045477185b9c5dbc5e367538` from `origin/codex/so101-act-data-0917a` and `github/codex/so101-act-data-0917a`.
- Registered evidence root: `/data/work/so101-evidence/act-main-refresh/20260924-e2ec-rebase` on ai-station.
- Writer policy: this local task is the only document writer. The required Astra reviewer is read-only. The ai-station recovery uses a new ordinary tmux shell session and does not launch `dst` or another implementation agent.

### Evidence boundary

The missing `/data/work/so101-evidence/act-data/0917a` root and prior worktree are not recoverable. Git can recover source history only. The refresh therefore rejects old episode/QC claims, introduces a new dataset/run boundary, and does not run camera, MuJoCo, MoveIt, collection, training, or robot acceptance. Rebase graph/readback and static document checks do not prove runtime correctness.

### Review log

| Round | Reviewer | Input hash | Result | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Astra high | Design `e8ca52283694d1ee4e88b4beb7d26d53058050e94e4ad984a1d2b07ac16e1a1a`; plan `76fbe7fe6d991e3176a391f120d6a7a7a440baa59e06252440f930c38502504e` | Not passed: 1 P1, 5 P2, 2 P3 | Single-stack collection bypassed global reservation; training had only a racy read-only GPU preflight; qualification required itself; multi-wave journal provenance and bundle paths were inconsistent; the full xdist gate was missing; dependency-lock and Linux queue references were stale. |
| 2 | Astra high | Design `1f406103c9835c065460846426c97ae756de1185956bec066816368d4affb4b3`; plan `ee881235cc2e3aab9524006c4457c74caf264eaf4f12c1b21b66157023cac30a` | Not passed: 1 P2, 1 P3 | GPU locks were keyed by selector rather than physical device identity, so index/UUID aliases could bypass mutual exclusion. The xdist commands also needed durable logs, elapsed time, separate exit codes, and explicit aggregate failure. |
| 3 | Astra high | Design `2d1db796d8ddfd20f63304ba3e976c7b07bef496c6fff265db4c3910195480ca`; plan `5fe40259879f03fa13c0bc5e50a5e0da1902f1e98bd170a5008b55936728b83c` | PASS: no P0/P1/P2/P3 | Physical GPU alias/mapping identity, durable xdist logs/elapsed/exit codes, and every prior finding were closed. Reviewer also parsed all 73 shell and 40 Python code blocks successfully. |
| 4 | Astra high | Design `2d1db796d8ddfd20f63304ba3e976c7b07bef496c6fff265db4c3910195480ca`; plan `5fe40259879f03fa13c0bc5e50a5e0da1902f1e98bd170a5008b55936728b83c` | PASS: no P0/P1/P2/P3 | Rebase reconciliation briefly considered retaining the old Task 1 checkmarks. Review rejected that: `cdd79d15` validates the old `pool_generation` result schema, while the refreshed plan requires batch, Worker generation, and coordinator commit identity. The final document therefore keeps Task 1 unchecked and exactly matches the Round 3 approved hash. |

### Evidence disposition

- Retained: registered ai-station root, this ledger, both updated documents, review findings, and future rebase transcript/readback.
- Archived: none.
- Deletion candidates: local `/tmp/act-rebase-resolution.patch`, `/tmp/act-remote-docs.m1IipE`, and `/tmp/act-doc-refresh.hsEpQu`; future pytest scratch only if implementation later runs the package gate. Do not delete without explicit authorization.
- Deletion performed: none.
