# robot_demo_001 Capture Owner Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the duplicate ai-station capture implementation from `robot_demo_001`, point current root documentation/Skills to moveit-demo’s `ai-station-gui` Skill, and update the moveit-demo submodule only after its new owner commit is published and fetchable.

**Architecture:** This is a separate parent-repository change executed in its own local worktree. The parent retains policy and project context but no capture code; the moveit-demo submodule owns the Skill/scripts. The submodule pointer advances only to a verified remote-fetchable commit containing the standalone Teleop and `ai-station-gui` work.

**Tech Stack:** Git worktrees/submodules, Markdown, Bash static checks, project-local Skills.

## Global Constraints

- Use a dedicated `robot_demo_001` worktree and preserve the clean/current `master` checkout and every user worktree.
- Delete `scripts/capture-ai-station.sh` and `scripts/ai-station-capture.py`; do not leave a wrapper or second implementation.
- Keep generic `cua-driver` reference material unless a separate reviewed change proves it obsolete.
- Current AGENTS/README/environment/Skill docs point to `moveit-demo/.agents/skills/ai-station-gui/` and explain agent+cua-driver priority.
- Do not rewrite historical specs, plans, handoffs, learning sessions, or experiment ledgers.
- Do not advance the submodule to an ai-station-only commit. The target commit must be published to the configured moveit-demo remote and fetchable from a fresh local fetch.
- Pushing a default branch or publishing the moveit-demo feature branch requires explicit user approval; do not infer that approval from implementation authorization.
- Preserve unrelated files, Obsidian state, caches, logs, captures, and local user changes.

---

### Task 1: Create and Audit the Parent Repository Worktree

**Files:**
- No source edit yet.

**Interfaces:**
- Produces: isolated local branch `codex/so101-teleop-root-migration` and an ownership snapshot for root/submodule.

- [ ] **Step 1: Re-read worktree and SO-101 project Skills.**

Read `superpowers:using-git-worktrees`, root `AGENTS.md`, and `.agents/skills/so101-dev/SKILL.md` before commands. This parent task is not a learning-progress write and does not modify the `learners/` tree.

- [ ] **Step 2: Verify root and submodule state.**

```bash
cd /Users/matianyi/Projects/robot_demo_001
git rev-parse HEAD
git branch --show-current
git status --short
git submodule status
git -C moveit-demo rev-parse HEAD
git -C moveit-demo status --short
```

Stop if root or submodule has overlapping user edits. Do not stash/reset/clean them.

- [ ] **Step 3: Create the isolated worktree from current `master`.**

Choose the repository’s ignored worktree area after verifying it with `git check-ignore`. Then create:

```bash
git worktree add .worktrees/so101-teleop-root-migration \
  -b codex/so101-teleop-root-migration master
```

Record the absolute path, HEAD, branch, `git status --short`, and submodule status from the new worktree.

- [ ] **Step 4: Commit nothing in this audit task.**

The worktree creation itself is not a source commit.

---

### Task 2: Lock the Single-Owner Contract with RED Checks

**Files:**
- Create: `scripts/test-ai-station-gui-owner.sh`

**Interfaces:**
- Produces: a temporary migration test that fails while duplicate root scripts/current references exist; it will be kept only if the repository uses shell contract tests, otherwise its assertions move into an existing validation location before final commit.

- [ ] **Step 1: Write a strict shell contract.**

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test ! -e "$repo_root/scripts/capture-ai-station.sh"
test ! -e "$repo_root/scripts/ai-station-capture.py"
test -f "$repo_root/moveit-demo/.agents/skills/ai-station-gui/SKILL.md"
test -f "$repo_root/moveit-demo/.agents/skills/ai-station-gui/scripts/capture-ai-station.sh"
test -f "$repo_root/moveit-demo/.agents/skills/ai-station-gui/scripts/ai-station-capture.py"
```

Add targeted current-doc assertions for `AGENTS.md`, `README.md`, `docs/ai-station-environment-setup.md`, `.agents/skills/so101-dev`, and `.agents/skills/so101-teleop-debug`; exclude `docs/superpowers`, `docs/handoffs`, and experiment records.

- [ ] **Step 2: Run and verify RED.**

```bash
bash scripts/test-ai-station-gui-owner.sh
```

Expected: FAIL because the two root scripts still exist and the stale local submodule does not yet contain the new Skill.

- [ ] **Step 3: Commit the RED test only if it is a durable repository check.**

If current repository conventions include `scripts/test-*.sh`, keep and commit it:

```bash
git add scripts/test-ai-station-gui-owner.sh
git commit -m "test: lock ai-station GUI ownership"
```

If no such convention exists, do not add a one-off executable permanently; keep the exact commands in the migration evidence and continue without a commit.

---

### Task 3: Delete Root Capture Code and Update Current Root References

**Files:**
- Delete: `scripts/capture-ai-station.sh`
- Delete: `scripts/ai-station-capture.py`
- Modify: `AGENTS.md`
- Modify: `docs/ai-station-environment-setup.md`
- Modify: `.agents/skills/so101-dev/references/ai-station-access.md`
- Modify: `.agents/skills/so101-dev/references/test-and-acceptance.md`
- Modify: `.agents/skills/so101-teleop-debug/SKILL.md` and current references only where capture/control is described
- Modify: `README.md` only if it exposes the old root command
- Modify: `scripts/test-ai-station-gui-owner.sh` if retained

**Interfaces:**
- Consumes: moveit-demo Skill path and its capture contract.
- Produces: parent repository with policy pointers but no implementation duplicate.

- [ ] **Step 1: Delete only the two approved implementation files.**

```bash
git rm -- scripts/capture-ai-station.sh scripts/ai-station-capture.py
```

Do not delete `skills/remote/cua-driver`, `.agents` CUA references, or unrelated scripts.

- [ ] **Step 2: Update root AGENTS GUI policy.**

Replace the obsolete `ai-station-capture.sh` instruction with an explicit pointer to:

```text
moveit-demo/.agents/skills/ai-station-gui/SKILL.md
```

State that the Skill first checks whether Codex/Claude/Kimi has a healthy loaded `cua-driver`; healthy CUA is preferred for screenshot/control, otherwise its script is screenshot-only fallback. Retain tmux, `~/gui-env.zsh`, no hard-coded DISPLAY, and visual-evidence rules.

- [ ] **Step 3: Update the active environment setup guide.**

Replace root-script installation/usage with:

```bash
moveit-demo/.agents/skills/ai-station-gui/scripts/capture-ai-station.sh --remote \
  --output-root /tmp/ai-station-evidence
```

Document direct-ai-station `--local` separately and state that a remote agent never SSHes itself. Explain desktop-required/window-optional behavior and null manifest fields.

- [ ] **Step 4: Update current project Skills without duplicating implementation.**

`so101-dev` and `so101-teleop-debug` should invoke/read the moveit-demo Skill, preserve their own SO-101/Teleop evidence gates, and use `snapshot -> action -> fresh snapshot`. Do not copy helper code or manifest schema into multiple Skills; link to the capture contract.

- [ ] **Step 5: Run current-surface scans before the submodule update.**

```bash
test ! -e scripts/capture-ai-station.sh
test ! -e scripts/ai-station-capture.py
rg -n "moveit-demo/.agents/skills/ai-station-gui" \
  AGENTS.md docs/ai-station-environment-setup.md .agents/skills
rg -n "scripts/capture-ai-station.sh|scripts/ai-station-capture.py|ai-station-capture.sh" \
  AGENTS.md README.md docs/ai-station-environment-setup.md .agents/skills
git diff --check
```

Expected: the first `rg` finds the new owner; the second finds no obsolete current-root implementation instruction. Do not use historical files in this failure gate.

- [ ] **Step 6: Commit root ownership cleanup separately.**

```bash
git add AGENTS.md README.md docs/ai-station-environment-setup.md .agents scripts
git commit -m "refactor: move ai-station capture ownership to moveit-demo"
```

---

### Task 4: Gate and Update the moveit-demo Submodule Pointer

**Files:**
- Modify: `moveit-demo` gitlink only.

**Interfaces:**
- Consumes: a published moveit-demo commit containing `src/so101_teleop` and `.agents/skills/ai-station-gui`.
- Produces: parent gitlink that any fresh clone can fetch.

- [ ] **Step 1: Stop for explicit publication approval.**

Before pushing the moveit-demo feature branch or any default branch, report the exact branch, commit range, tests, and unrelated scope. Proceed only after the user explicitly approves that push/merge.

- [ ] **Step 2: After publication, fetch and identify the remote-fetchable target.**

```bash
git -C moveit-demo fetch origin
teleop_target_commit=$(git -C moveit-demo rev-parse origin/codex/so101-teleop-extraction)
git -C moveit-demo cat-file -e "$teleop_target_commit^{commit}"
```

If the implementation was merged to remote `main`, resolve `origin/main` instead and verify that it contains the feature commit with `git merge-base --is-ancestor`.

- [ ] **Step 3: Verify target content before changing the gitlink.**

```bash
git -C moveit-demo show "$teleop_target_commit:.agents/skills/ai-station-gui/SKILL.md" >/dev/null
git -C moveit-demo show "$teleop_target_commit:src/so101_teleop/package.xml" >/dev/null
git -C moveit-demo show "$teleop_target_commit:src/so101_gazebo_demo_cpp/launch/so101_teleop.launch.py" >/dev/null 2>&1 && exit 1 || true
```

Expected: new Skill and package exist; old C++ Teleop launch does not.

- [ ] **Step 4: Checkout the exact commit in the submodule and rerun ownership checks.**

```bash
git -C moveit-demo checkout --detach "$teleop_target_commit"
bash scripts/test-ai-station-gui-owner.sh
git status --short
git diff --submodule=log
```

If the shell test was not retained, execute its exact assertions manually.

- [ ] **Step 5: Commit only the gitlink update.**

```bash
git add moveit-demo
git commit -m "chore: update moveit-demo for standalone Teleop"
```

---

### Task 5: Final Parent-Repository Verification and Handoff

**Files:**
- No expected source change.

**Interfaces:**
- Produces: clean parent branch whose current docs and gitlink agree with the single owner.

- [ ] **Step 1: Verify no unintended local-state files are staged.**

```bash
git diff --cached --name-only
git diff --cached --check
git status --short
```

Reject `.obsidian/workspace.json`, `.obsidian/appearance.json`, captures, caches, logs, and unrelated learner/session files.

- [ ] **Step 2: Verify root/submodule provenance and remote availability.**

```bash
git rev-parse HEAD
git branch --show-current
git submodule status
git -C moveit-demo rev-parse HEAD
git -C moveit-demo branch -r --contains HEAD
git -C moveit-demo status --short
```

Require at least one expected remote branch to contain the submodule commit; a local-only commit is not acceptable.

- [ ] **Step 3: Verify current docs and ownership one final time.**

```bash
test ! -e scripts/capture-ai-station.sh
test ! -e scripts/ai-station-capture.py
test -f moveit-demo/.agents/skills/ai-station-gui/SKILL.md
test -f moveit-demo/.agents/skills/ai-station-gui/scripts/capture-ai-station.sh
test -f moveit-demo/.agents/skills/ai-station-gui/scripts/ai-station-capture.py
rg -n "moveit-demo/.agents/skills/ai-station-gui" \
  AGENTS.md docs/ai-station-environment-setup.md .agents/skills
git diff --check master...HEAD
```

- [ ] **Step 4: Report without pushing the parent default branch.**

Report parent branch/commits, moveit-demo target commit/remote containment, deleted files, updated current docs, checks, and preserved user work. Offer a separate explicit push/merge action; do not push `master` implicitly.
