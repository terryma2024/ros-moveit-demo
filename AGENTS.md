# Repository Rules

- Write all README files in this repository in English. Keep commands, identifiers, paths, API
  names, and other source literals unchanged.
- When writing or substantially revising persistent, human-facing documentation such as README
  files, guides, manuals, and tutorials, use the project-local `$humanizer-zh` skill for Chinese
  prose and `$humanizer` for English prose. Do not apply these skills to ledgers, logs, generated
  evidence, temporary notes, or other audit- or machine-oriented records. Preserve technical facts,
  commands, identifiers, paths, API names, code, data, citations, and link targets unchanged.
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
- The `origin` remote is hosted on Gitee, not GitHub.
- Do not use the `gh` CLI for remote push, pull request, or repository operations in this workspace.
- Use standard Git commands for remote operations, for example `git push origin <branch>`.
- Do not run `ament_uncrustify --reformat`. Use it only for read-only checks; make any required
  formatting changes explicitly with targeted patches.
