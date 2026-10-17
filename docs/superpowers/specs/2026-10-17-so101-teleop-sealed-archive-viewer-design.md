# SO-101 Teleop: sealed archive viewer — design

Status: DRAFT for the human, 2026-10-17. Requirements: `2026-10-17-so101-teleop-sealed-archive-viewer-requirements.md`. The execution plan goes to Codex, who verifies every file and line reference below before relying on it.

## 1. Where it fits

- **Backend.** The unified Teleop server is one FastAPI app (`src/so101_teleop/so101_teleop/unified/app.py`) with one port and one web bundle.
  - Routes are registered in this order: API and WebSocket routes, the instance channel, health, static assets, page paths, then the SPA fallback.
  - The OpenAPI document is exported (`openapi_export.py`, `unified_openapi.json`), and the web client has generated types (`web/src/api/unified-schema.d.ts`).
- **Frontend.** `src/so101_teleop/web` uses React 18.3, Vite 5, Tailwind 3 and shadcn-style components (`web/src/components/ui`).
  - `main.tsx` renders `AppShell` with three pages chosen by `usePageRouting()`: teleop, tasks and validation.
  - Each page has a client in `web/src/api/*-client.ts`.
- **The viewer adds** a fourth page, `archives`, and a read-only router mounted at `/api/archives`.
  - The router has no dependency on ROS, the domain runtimes or the instance channel.

## 2. Data sources

Paths are relative to a collection package root P, for example `REG/act-w8f-20261017T021838Z`.

| Need | Source | Notes |
| --- | --- | --- |
| Seal metadata | `P/SEALED.json` | `reason`, `sealed_at`, `files`, `bytes`, `manifest`, `manifest_sha256` |
| File list, sizes, sha | `P.seal-manifest.jsonl` (sibling of P) | One JSON line per file, about 140k lines. Indexed once into memory; also gives the per-episode file table. |
| Registry membership | `REG/SEALED-ROOTS.json` | Optional; listed packages show "registered". |
| Committed episodes | `P/collection-index.json` | Schema 2 or 3. `committed_episodes[]` with `scene_id` and `collection_evidence` (absolute paths: `processing_output`, `owner_root`, `registration`, `result_location`, `inputs_manifest`). Schema 3 adds `collected_tasks[]` with `recording_round`, `wave_index` and `final`. |
| All scenes, final outcome, attempts | `P/host/campaign-result.json` | `scenes[]` with `attempts[]` (outcome, reason, `proc_attempt`, `processor_id`, `output_dir`), `phase1` (`teacher_task_result`, `recording_bytes`), `counts` and `rounds` (when retry ran). |
| Retry rounds | `P/host/retry-round-<r>.json` | Status, candidates and plans. |
| Scene split, seed, cup | the formal scene list | Found through `P/inputs/frozen/inputs-manifest.json`, or the campaign's inputs directory. Codex must find the reliable link; the inputs directory is a separate sealed root. |
| Campaign identity and settings | `P/campaign-index.json`, `P/inputs/frozen/*`, `P/host/resources.jsonl` | Images, commit, cap and processors. Show what is present and do not fail on what is absent. |
| Episode seal | `<processing_output>/episode/seal.json` | `status`, `qc_passed`, `pick_place_validation_success`, `record_count`, `committed`, `stopped_confirmed`, `files` |
| Processed result | `<processing_output>/processed-result.json` | `act_data_status`, `export_eligible`, `proc_attempt`, `qc_report_path` |
| QC report | `<processing_output>/qc-report.json` | Shown formatted. |
| Rows | `<processing_output>/episode/records.jsonl` | About 905 lines and 15 MB. Each line has `action` (6 floats), `observation.state`, `observation.sim_time_s`, `observation.head_png` and `observation.wrist_png` (frame file names), and an `audit` object that is large and not sent to the client. |
| Frames | `<processing_output>/episode/frames/NNNNNN-{head,wrist}.png` | 640×480 RGB PNG, about 66 KB each. |
| Audit | `<processing_output>/episode/audit/*.jsonl` | `events.jsonl` is about 300 MB. Paged by byte offset only. |

**Path rule.** Every absolute path found in these documents must resolve inside P after `realpath`. Anything else is refused and shown as "outside package". The server builds a per-package map from scene id to its `processing_output` and never accepts a path from the client.

## 3. Backend

New package `src/so101_teleop/so101_teleop/archive_viewer/`.

**`config.py`**
- The search roots come from a CLI option or environment variable of the unified server, for example `--archive-root PATH`, repeatable.
- With none, the router reports `enabled: false`.
- Roots must be absolute, existing directories.

**`scan.py`**
- Walks a search root with `os.scandir`. It stops descending at a directory that contains `SEALED.json`, and skips symlinked directories.
- It reads `SEALED.json` and checks for `collection-index.json` (kind collection or supporting).
- It joins the result with `SEALED-ROOTS.json` if present at the search root.
- The result is cached in memory with the directory mtimes and refreshed on request.
- The package id is a stable hash of the resolved path, for example its first 16 hex digits. It is opaque to the client.

**`package.py`**
- Lazily loads and caches, per package:
  - the seal manifest index, a dict from relative path to bytes and sha;
  - `collection-index`;
  - `campaign-result`;
  - the retry-round files;
  - the scene list.
- It builds the statistics and episode rows of R2. Duration comes from the seal's `record_count` at 10 Hz; size is the sum of the episode's manifest entries.
- Everything is computed from the documents; nothing is written.

**`episode.py`**
- Builds the detail of R3.
- `records.jsonl` is read line by line. Only `action`, `observation.state`, `sim_time_s` and the frame names are kept, without `audit`.
- Series are downsampled with a fixed stride, at most about 2,000 points.
- Frame lookup is by row index, through the frame names in the row, and the frame file must be inside `episode/frames`.

**`files.py`**
- Serves the manifest-listed files of an episode by file id: the index into the episode's manifest entries, or a hash of the relative path.
  - JSON of 2 MB or less is returned whole.
  - A `.jsonl` is returned as a page `(offset_bytes, limit_lines)` that returns the lines and the next offset.
- Files are opened with `open(path, 'rb')`. Nothing else is used, and no file is created.

**`verify.py`**
- One background job at a time, in a thread.
- It re-hashes every manifest entry and keeps progress counts in memory: checked, mismatched, missing. It can be cancelled.

**`api.py`, the router.** It is registered with the other API routers, before the SPA fallback.

| Method and path | Returns |
| --- | --- |
| `GET /api/archives/config` | `{enabled, roots:[{root_id, label}]}` |
| `GET /api/archives/packages?root_id=&refresh=` | Package list (R1.4) |
| `GET /api/archives/packages/{package_id}` | Seal metadata, identity, statistics (R2.2) |
| `GET /api/archives/packages/{package_id}/episodes?split=&outcome=&q=&sort=&offset=&limit=` | Episode rows (R2.3/R2.4) |
| `GET /api/archives/packages/{package_id}/episodes/{scene_id}` | Detail: summary, attempts, file table, frame count (R3.2/R3.3/R3.6) |
| `GET /api/archives/packages/{package_id}/episodes/{scene_id}/series` | Downsampled `t`, `action[6]`, `state[n]`, with the stride |
| `GET /api/archives/packages/{package_id}/episodes/{scene_id}/frames/{row}/{camera}` | `image/png`, served as a file response with `Cache-Control: private, max-age=3600` |
| `GET /api/archives/packages/{package_id}/episodes/{scene_id}/files/{file_id}?offset=&limit=` | JSON content, or a page of a `.jsonl` |
| `POST /api/archives/packages/{package_id}/verify`, `GET .../verify`, `DELETE .../verify` | Start, read progress, cancel |

- **Models** are Pydantic models with `extra='forbid'`, in the same style as `unified/contracts.py`.
- **OpenAPI:** regenerate `unified_openapi.json` and the web client types through the repository's existing export path.
- **Errors:**
  - an unknown id gives 404;
  - a path outside the package gives 409 `ARCHIVE_PATH_OUTSIDE_PACKAGE`;
  - a malformed document gives 422 with the document name;
  - when the feature is disabled, the router answers 404 `ARCHIVES_DISABLED`.

## 4. Frontend

- **`web/src/api/archives-client.ts`:** typed calls over the generated schema, following the pattern of `task-client.ts`.
- **Routing:**
  - add page `archives` to the page router and to the `AppShell` navigation;
  - sub-state lives in the URL query (`?page=archives&root=…&pkg=…&scene=…`), so detail pages can be reloaded (R3.1). Follow how `usePageRouting` encodes pages.
- **Components** in `web/src/components/archives/`:
  - **`ArchiveBrowser`:** chooses the root, lists packages in a table (R1.4) and has a refresh button.
  - **`PackageView`:** stat cards (R2.2), the verify button with progress (R4), and an episode table with filters, sort and search (R2.3/R2.4). Rows link to the detail page.
  - **`EpisodeDetail`:** a summary card, an attempts timeline (a simple vertical list), a frame player and signal charts.
    - The frame player shows two `<img>` side by side with a range slider and play/pause at 10 Hz. It prefetches the next few frames.
    - Each signal chart is a small inline-SVG line chart, one per group (action 6, state n), with a shared cursor bound to the slider. The project has no charting library; do not add one unless Codex finds one already present.
    - The files table opens JSON in a dialog. `.jsonl` opens in a paged view.
- Style and components follow `web/src/components/ui` and the existing pages, and work in the existing light and dark themes.

## 5. Tests

**Backend** (`src/so101_teleop/test/...`, pytest):
- A fixture builder writes a synthetic sealed collection package into `tmp_path`:
  - `SEALED.json` and the manifest;
  - a `collection-index.json` of schema 3 with one retried scene;
  - a `campaign-result.json` with VALID, INVALID-recovered and FAULT scenes;
  - two episodes with 5 rows each, tiny PNGs and a large-ish `events.jsonl`.
- **Read-only proof:** make the fixture read-only (`chmod -R a-w`), exercise every endpoint, then assert that the tree listing and mtimes are unchanged.
- **Path safety:**
  - an episode whose `processing_output` points outside the package;
  - a symlinked frame leading outside;
  - an unknown file id.
- **Scan:**
  - nested packages are not descended;
  - supporting packages;
  - an unsealed run directory is ignored;
  - a missing `SEALED-ROOTS.json`.
- **Statistics:** counts by split and outcome, recovered by retry, durations.
- **Paging:** `.jsonl` offsets, and a line longer than the page.
- **Verify:** a clean pass, a mismatch after a fixture byte change (made on a separate writable copy), and cancel.
- **Feature disabled:** when no search root is configured, the router answers 404.

**Frontend** (vitest): the client against fixtures, the package table filters, and the detail page slider driving the frame URL and the chart cursor. An optional Playwright check against the installed server with a fixture root.

The ordinary Teleop test gate must not read `/data/work`. A manual acceptance run against the real registry follows the requirements' Acceptance section.

## 6. Risks and decisions for the plan

- **Linking a collection package to its scene list and inputs.** The inputs are a separate sealed root. Codex must find the reliable link (`inputs-manifest.json` or `campaign-index`) and fall back to showing the scene id only.
- **Absolute paths inside the indexes.** They point into the same package today. If a package is ever moved, the viewer should resolve them relative to the package by replacing the recorded root prefix. Recommended: support that from the start.
- **Manifest size.** About 140k lines per package means about 30 MB in memory per loaded package. Keep at most a few packages loaded (LRU).
- **Serving PNGs.** Use a file response from a validated path. Do not convert, and do not create thumbnails on disk.
- **Bind policy.** The archive routes expose evidence content, so they inherit the server's existing bind and authentication policy unchanged.
