# Repository Rules

- Write all README files in this repository in English. Keep commands, identifiers, paths, API
  names, and other source literals unchanged.
- When writing or substantially revising persistent, human-facing documentation such as README
  files, guides, manuals, and tutorials, use the project-local `$humanizer-zh` skill for Chinese
  prose and `$humanizer` for English prose. Do not apply these skills to ledgers, logs, generated
  evidence, temporary notes, or other audit- or machine-oriented records. Preserve technical facts,
  commands, identifiers, paths, API names, code, data, citations, and link targets unchanged.
- Store all persistent teaching guides and source walkthroughs under `docs/guides/`. Do not add new
  teaching-guide files directly under `docs/`.
- When developing, modifying, debugging, testing, or visually validating any SO-101 application in
  this repository, you must use the project-local `$so101-dev` skill at
  `.agents/skills/so101-dev/SKILL.md` before taking task actions and follow its workflow and evidence
  gates.
- Every SO-101 task must use one registered evidence root. Put ordinary low-rate logs in a unique
  `/tmp/so101-debug-<task-id>/`. Put high-frequency lossless evidence or artifacts requiring durable
  retention only in `/data/work/so101-evidence/<task-family>/<run-id>/`; put superseded but auditable
  batches in `/data/work/so101-evidence/archived/<task-family>/<run-id>/`. Never create a direct
  `/data/work/so101-debug-*` path. Register the root in the task ledger, and at completion report
  retained runs, archived runs, and deletion candidates. Do not delete evidence without explicit
  user authorization.
- On `ai-station` only, any pytest or benchmark run that creates fsync-heavy temporary fixtures must
  use a unique, previously nonexistent scratch directory on the `/data` NVMe filesystem under the
  task's registered durable evidence root, for example
  `/data/work/so101-evidence/<task-family>/<run-id>/scratch/<test-run-id>/tmp`. Before starting
  `pytest` or `colcon test`, set `TMPDIR`, `TMP`, and `TEMP` to that directory and use the exact test
  Python executable to verify that `tempfile.gettempdir()` resolves inside it; fail closed if it
  does not. Record the scratch path and elapsed time with the test evidence, classify the scratch
  tree as a deletion candidate after readback, and do not delete it without explicit user
  authorization. Do not apply this `/data` path rule on macOS or other hosts, and do not disable
  `fsync`, filesystem journaling, or integrity checks or substitute `tmpfs` to make the test faster.
- The default interactive shell in this workspace is `zsh`. Do not assign to zsh special or
  read-only parameters such as `status`; store an exit code in a task-specific name such as `rc` or
  `test_rc` instead.
- When a command whose result matters is piped through `tee` or another process, enable
  `set -o pipefail` before running it. `set -e` alone does not prevent the final process in a
  pipeline from hiding an earlier failure. Record and check the actual command exit code before
  reporting success.
- Do not pass an optional unmatched glob directly to a command under zsh, because zsh fails with
  `no matches found` before the command starts. Prefer `rg` with `-g`, `find` with `-name`, or an
  explicit existence check.
- Before starting a long-running service or test, resolve and verify the exact executable and
  environment paths with read-only checks such as `test -x`. Do not rely on a summarized or older
  virtual-environment path when the filesystem can provide the current path.
- A fresh colcon `--build-base` or `--install-base` must have a complete dependency closure. Before
  treating a failed build as a source regression, distinguish missing package setup files,
  incomplete underlays, package-selection errors, and override errors from compiler or test
  failures. Do not count a test as RED unless the intended test or code boundary actually ran.
- A sandbox denial for the Docker socket, network namespace, or host process metadata does not prove
  that the corresponding resource is absent. Repeat the read-only check with the approved host
  access required by the task, then base cleanup and ownership conclusions on that result.
- If a tool call or shell session is interrupted, inspect its process state, logs, and declared
  outputs before retrying. An interrupted poll is not evidence that the underlying command failed,
  succeeded, or stopped.
- This repository uses the following remote mapping:
  - `origin`: `git@gitee.com:zjumty/ros-moveit-demo.git`
  - `github`: `git@github.com:terryma2024/ros-moveit-demo.git`
- Gitee `origin/main` maps to GitHub `github/main`. When copying published changes between them,
  preserve commits that exist on only one remote and do not force-push either branch.
- Do not use the `gh` CLI for remote push, pull request, or repository operations in this workspace.
- Use standard Git commands for remote operations, for example `git push origin <branch>`.
- Do not run `ament_uncrustify --reformat`. Use it only for read-only checks; make any required
  formatting changes explicitly with targeted patches.
- Keep low-frequency perception comparison tests under `src/so101_demo_py/benchmark_test/`. The
  ordinary `so101_demo_py` test gate must use `src/so101_demo_py/test/` and must not collect the
  benchmark suite.
- Run the benchmark test suite explicitly only when changing benchmark implementation,
  configuration, adapters, reports, or tests, or while selecting/comparing perception models. Use
  `colcon test --packages-select so101_demo_py --pytest-args benchmark_test` for that explicit gate.
  Ordinary feature work outside those scopes must not run the benchmark suite.

## Task model selection

| Task | Required model or tool |
| --- | --- |
| Discuss approaches; write designs, implementation plans, and guides | GPT-6 Sol / High (`gpt-6-sol`, reasoning effort `high`) |
| Independently review approaches, designs, implementation plans, and guides | GPT-6 Astra / High (`gpt-6-astra`, reasoning effort `high`) |
| Execute implementation plans | DeepSeek Harness TUI, launched with `dst` in a `tmux` session |
| Monitor execution and review execution results | GPT-6 Sol / High (`gpt-6-sol`, reasoning effort `high`) |
| Other tasks (default) | GPT-6 Sol / High (`gpt-6-sol`, reasoning effort `high`) |

- Use an independent GPT-6 Astra / High reviewer for the review tasks listed above.
- If a required model or tool is unavailable, report the limitation explicitly. Do not silently
  substitute another model or tool or automatically switch to a lower-capability model.
- These task rules do not authorize changes to global default model configuration.
