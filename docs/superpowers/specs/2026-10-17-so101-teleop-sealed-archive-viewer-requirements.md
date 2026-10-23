# SO-101 Teleop: sealed archive viewer — requirements

Status: DRAFT for the human, 2026-10-17. Design: `2026-10-17-so101-teleop-sealed-archive-viewer-design.md`. The execution plan and its implementation go to Codex.

## Background

Formal ACT collections are sealed after they finish. The first sealed collection is EXP-620, with 69 committed episodes. A sealed root contains:
- `SEALED.json`;
- a per-file sha256 manifest (`<root>.seal-manifest.jsonl`, next to the root);
- read-only files;
- an entry in `REG/SEALED-ROOTS.json`.

Today the only way to look at what is inside is with shell scripts. The human wants a viewer in the Teleop web app that works per episode.

Human request (2026-10-17): "想在teleop系统里增加一个封存记录查看器，以episode为单位查看。指定目录里自动搜索封存包。选择封存包，显示episode列表和统计信息。选择episode进入episode详细页。"

## Users and use

One operator on the workstation, using the Teleop web app in a browser. They use it to:
- check what a sealed collection holds before training;
- spot-check episodes visually;
- see why a scene is missing or was retried.

## Functional requirements

### R1. Search a directory for sealed packages

- **R1.1** The operator chooses a search directory from a list that the server is configured with, for example the evidence registry root. The server finds every sealed package below it automatically.
- **R1.2** A sealed package is a directory that contains a `SEALED.json` of kind `SEALED_EVIDENCE_ROOT`. A package that also holds a `collection-index.json` is a collection package. Its episodes can be browsed.
- **R1.3** Other sealed roots, such as inputs, qualification runs, gate installs and image builds, are listed as supporting packages. They show only their seal metadata, with no episode browsing.
- **R1.4** For each package the list shows:
  - its name (the directory name) and its kind (collection or supporting);
  - when it was sealed and why (`SEALED.json` `reason`);
  - its file count and total size;
  - its manifest sha256;
  - whether it appears in `SEALED-ROOTS.json`.
- **R1.5** A refresh action searches again. Searching must not take more than a few seconds for the registry, and must not descend into a package once the package has been found.

### R2. Package page: episode list and statistics

- **R2.1** Selecting a collection package shows its statistics and its episode list.
- **R2.2** Statistics:
  - scenes planned, committed episodes, and scenes not committed, by state (FAULT, MISSING, INVALID as final);
  - committed episodes by split (train, validation, offline_test);
  - retry: recording rounds run and scenes recovered by a retry;
  - totals and medians of episode duration (rows at 10 Hz) and episode size;
  - campaign identity: campaign id, commit, image digests, qualification report sha, settings (recording cap, processors, retry rounds), and the run's start and end times.
- **R2.3** The episode list has one row per scene of the formal list, committed or not. Columns:
  - scene id, split and committed (yes or no);
  - final outcome (VALID, INVALID, FAULT, MISSING) and its reason, shortened;
  - the number of recording attempts, and the round of the final attempt;
  - duration (rows and seconds), size, Teacher result and QC status.
- **R2.4** The list can be filtered by split and by outcome, sorted by any column, and searched by scene id.

### R3. Episode detail page

- **R3.1** Selecting an episode opens its detail page. It has its own URL, so the page can be reloaded or shared on the workstation.
- **R3.2** Summary:
  - scene id, split, seed and cup position;
  - the seal (status, `qc_passed`, `pick_place_validation_success`, `record_count`, `committed`, `stopped_confirmed`);
  - the processed result (`act_data_status`, `export_eligible`, processor attempt);
  - the QC report summary.
- **R3.3** Attempts timeline: every recording attempt and every processing attempt of the scene, each with its round, wave, shard, outcome and reason. This includes attempts that did not become final.
- **R3.4** Camera frames:
  - head and wrist frames are shown side by side;
  - a slider and play/pause step through the episode's rows;
  - the current row index and `sim_time_s` are displayed;
  - frames load lazily.
- **R3.5** Signals: charts over time of the 6-value `action` and of the joint state in `observation.state`. A cursor stays in sync with the frame slider.
- **R3.6** Files: the episode's files with their size and sha256, taken from the seal manifest. The operator can open small JSON files, such as the seal, QC report and processed result, as formatted text.
- **R3.7** Large audit files, such as `audit/events.jsonl` (about 300 MB), are offered as a paged view (first N lines, next page). They are never loaded whole.

### R4. Integrity check (optional, on demand)

- **R4.1** On the package page, a "verify" action re-hashes the package's files against its seal manifest. It shows progress and the result: files checked, mismatches and missing files.
- **R4.2** It runs in the background, one at a time, and can be cancelled.

## Non-functional requirements

- **N1, read-only.**
  - The viewer never writes, renames, deletes or creates anything inside a sealed package or its manifest.
  - All files are opened read-only.
  - No cache, temporary or index file is placed in the package. Any cache lives in memory, or in the server's own state directory outside the evidence roots.
- **N2, path safety.**
  - The client never sends a filesystem path, only ids that the server issued (package id, scene id, frame index, file id from the manifest).
  - The server resolves every path inside the selected package and refuses symlinks that lead outside it.
- **N3, scale.**
  - A collection package has about 140,000 files and 50 GB. A package page must load in under 3 s, cold under 10 s.
  - Frames are served one at a time.
  - Signals are downsampled for the chart (at most about 2,000 points per series).
- **N4, no new runtime dependency on ROS or Docker.** The viewer reads files only.
- **N5, works with the server's existing security.** It runs on the same port and bind policy as the rest of the Teleop server, and is disabled when no search directory is configured.
- **N6, tests.** Tests fixture their own synthetic sealed packages and never read `/data/work` files.

## Out of scope

- Editing, unsealing, deleting or exporting episodes.
- Training or dataset merge. The merge of the 69 and supplementary episodes is a separate tool.
- Playing raw mcap bags, and visualising contacts or 3D state.
- Packages that are not sealed. A future option could allow browsing any run directory read-only.

## Acceptance

- Pointed at the registry, the viewer lists the seven current sealed roots. EXP-620 shows 70 scenes, 69 committed (49/10/10), 1 FAULT (`frm-007`) and 5 recovered by retry round 1.
- `frm-000`'s detail page plays its 905 rows of head and wrist frames, with action and state charts in sync.
- After a full session of browsing, a byte-level verify of EXP-620 reports no change, and nothing new appears inside any sealed root.
