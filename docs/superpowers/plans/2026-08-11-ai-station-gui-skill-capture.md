# ai-station-gui Skill and Capture Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make moveit-demo the single long-term owner of an `ai-station-gui` Skill that prefers a healthy Codex/Claude/Kimi `cua-driver` path and provides a deterministic full-desktop-first screenshot fallback when GUI windows are absent.

**Architecture:** The Skill decides whether execution is directly on ai-station and whether the current agent has a genuinely loaded, healthy `cua-driver` screen-control capability. Healthy CUA uses `snapshot -> action -> fresh snapshot`; otherwise `capture-ai-station.sh` invokes the colocated Python helper locally or through an explicit Mac/orchestrator SSH path. Desktop capture is required; RViz/Ghostty captures are optional manifest fields and never cause failure merely because the windows do not exist.

**Tech Stack:** Codex/Claude/Kimi Skill conventions, Bash, Python 3.12, Pillow `ImageGrab`, X11/Xlib/XTest, pytest, SSH/SCP, JSON manifests.

## Global Constraints

- Implement in `/data/work/ws_moveit/.worktrees/so101-teleop-extraction` and do not disturb existing tmux, Gazebo, MoveIt, RViz, MuJoCo, or physical-five-success processes.
- The Skill must check usable agent/tool capability, not merely the existence of a `cua-driver` binary or directory.
- An agent already running on ai-station must never SSH to ai-station itself.
- CUA screen control must use `snapshot -> action -> fresh snapshot`; element indices cannot cross snapshots.
- Script fallback provides screenshot capture only and must not claim semantic mouse/keyboard/UI control.
- Full-screen `desktop.png` is the only mandatory artifact. RViz, Ghostty, and all other window captures are optional.
- When RViz and Ghostty are both absent, capture a fresh desktop, emit a valid manifest, and exit `0`.
- `--test-ghostty-tabs` must send no key if Ghostty is absent, record `skipped_no_window`, and exit `0`.
- Never copy null paths, create zero-byte placeholder files, reuse stale files, or write captures into the source tree.
- Current Skills/operator docs may change; historical specs, plans, handoffs, and experiment ledgers remain unchanged.

---

## File Structure

```text
.agents/skills/ai-station-gui/
├── SKILL.md                               # Host/agent/CUA routing and fallback workflow
├── agents/openai.yaml                     # Discovery metadata
├── references/capture-contract.md         # Manifest, exit-code, and evidence contract
├── scripts/capture-ai-station.sh          # Local-ai-station or remote-orchestrator wrapper
├── scripts/ai-station-capture.py          # Full desktop plus optional window captures
└── test/
    ├── test_ai_station_capture.py         # Python helper behavior matrix
    ├── test_capture_wrapper.py             # Wrapper null-copy/local-vs-remote behavior
    └── test_skill_contract.py              # Required routing language and paths
```

---

### Task 1: Establish the Skill Contract and Discovery Metadata

**Files:**
- Create: `.agents/skills/ai-station-gui/SKILL.md`
- Create: `.agents/skills/ai-station-gui/agents/openai.yaml`
- Create: `.agents/skills/ai-station-gui/references/capture-contract.md`
- Create: `.agents/skills/ai-station-gui/test/test_skill_contract.py`

**Interfaces:**
- Produces: discoverable Skill name `ai-station-gui`, explicit routing decision, and stable manifest/exit contract for scripts/tests/docs.

- [ ] **Step 1: Write a RED contract test for required Skill routing.**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_skill_prefers_loaded_agent_cua_before_script_fallback():
    text = (ROOT / "SKILL.md").read_text()
    required = (
        "Codex", "Claude", "Kimi", "cua-driver",
        "snapshot -> action -> fresh snapshot",
        "直接运行在 ai-station", "不得 SSH 自身",
        "scripts/capture-ai-station.sh",
    )
    assert all(value in text for value in required)
    assert text.index("cua-driver") < text.index("scripts/capture-ai-station.sh")


def test_capture_contract_makes_only_desktop_required():
    text = (ROOT / "references" / "capture-contract.md").read_text()
    assert "desktop" in text
    assert '"rviz": null' in text
    assert '"ghostty": null' in text
    assert "skipped_no_window" in text
```

- [ ] **Step 2: Run the test and verify RED.**

```bash
cd /data/work/ws_moveit/.worktrees/so101-teleop-extraction
PYTHONNOUSERSITE=1 pytest -q .agents/skills/ai-station-gui/test/test_skill_contract.py
```

Expected: FAIL because the Skill files do not exist.

- [ ] **Step 3: Write the Skill routing procedure.**

`SKILL.md` must require these ordered checks:

1. Determine whether the current agent is directly on ai-station from hostname/workspace evidence; never infer this from SSH alias resolution.
2. Identify the current agent as Codex, Claude, or Kimi from the live execution context.
3. Inspect the current tool/Skill inventory for a loaded `cua-driver` screen capability and its live schema.
4. Probe driver/desktop/session permission health using that schema; a file or executable alone is insufficient.
5. If healthy, use agent+cua-driver for screenshots and control, always `snapshot -> action -> fresh snapshot`.
6. If absent/degraded/unusable, call the colocated script fallback and state that it captures only screenshots.

Include a stop rule: if screen control is required but only script capture is available, capture evidence and report control as unavailable rather than injecting X11 keys.

- [ ] **Step 4: Define the exact manifest and exit codes.**

`capture-contract.md` must define:

```json
{
  "captured_at": "2026-08-11T12-00-00",
  "desktop": "/tmp/evidence/desktop.png",
  "rviz": null,
  "ghostty": null,
  "captured_windows": [],
  "missing_windows": ["rviz", "ghostty"],
  "capture_mode": "desktop_only",
  "ghostty_tab_test": "not_requested"
}
```

Exit `0` for every valid desktop capture regardless of optional windows. Exit nonzero only for desktop failure, invalid manifest, or failed transfer of an artifact the manifest declared.

- [ ] **Step 5: Add discovery metadata, run GREEN, and commit.**

Use concise metadata that names screenshot and GUI control on ai-station and routes users to the Skill. Then run:

```bash
PYTHONNOUSERSITE=1 pytest -q .agents/skills/ai-station-gui/test/test_skill_contract.py
git add .agents/skills/ai-station-gui
git commit -m "docs: define ai-station GUI skill contract"
```

---

### Task 2: Migrate and Fix the Python Screenshot Helper

**Files:**
- Create from parent-repo source: `.agents/skills/ai-station-gui/scripts/ai-station-capture.py`
- Create: `.agents/skills/ai-station-gui/test/test_ai_station_capture.py`

**Interfaces:**
- Consumes: active GNOME X11 environment and window inventory.
- Produces: `capture_session(output_root, test_ghostty_tabs=False, *, environment_loader=find_gnome_environment, window_loader=list_windows, desktop_grabber=grab_desktop, window_grabber=capture_window, manager_factory=X11WindowManager) -> dict[str, object]` and CLI JSON manifest.

- [ ] **Step 1: Transfer the current helper as migration input without editing the parent copy.**

From the Mac/orchestrator, run once:

```bash
scp /Users/matianyi/Projects/robot_demo_001/scripts/ai-station-capture.py \
  ai-station:/data/work/ws_moveit/.worktrees/so101-teleop-extraction/.agents/skills/ai-station-gui/scripts/ai-station-capture.py
```

Do not run this command from an agent already on ai-station.

- [ ] **Step 2: Write the four-combination RED matrix with injected fakes.**

Refactor boundaries must be injectable so tests do not require a real display. Cover:

```python
def fake_desktop_png(_display_name: str, output_path: Path) -> None:
    output_path.write_bytes(b"desktop-png")


def fake_window_png(_manager, _window, output_path: Path, _display_name: str) -> None:
    output_path.write_bytes(b"window-png")


class FakeWindowManager:
    def __init__(self, _display_name: str):
        self.shortcuts = []

    def send_shortcut(self, modifiers, key):
        self.shortcuts.append((modifiers, key))

    def close(self):
        return None


@pytest.mark.parametrize(
    "present,expected_mode,expected_missing",
    [
        ({"rviz", "ghostty"}, "desktop_and_windows", []),
        ({"rviz"}, "desktop_and_windows", ["ghostty"]),
        ({"ghostty"}, "desktop_and_windows", ["rviz"]),
        (set(), "desktop_only", ["rviz", "ghostty"]),
    ],
)
def test_optional_window_matrix(present, expected_mode, expected_missing, tmp_path):
    windows = [
        {"id": 1, "description": name, "width": 800, "height": 600, "x": 0, "y": 0}
        for name in sorted(present)
    ]
    manifest = capture_session(
        tmp_path,
        environment_loader=lambda: {"DISPLAY": ":1"},
        window_loader=lambda: windows,
        desktop_grabber=fake_desktop_png,
        window_grabber=fake_window_png,
        manager_factory=FakeWindowManager,
    )
    assert manifest["capture_mode"] == expected_mode
    assert manifest["missing_windows"] == expected_missing
```

Also test that every non-null manifest path exists, is fresh within the current output directory, and has nonzero bytes.

- [ ] **Step 3: Add RED tests for Ghostty tab safety.**

```python
def test_tab_test_skips_without_ghostty_and_sends_no_key(tmp_path):
    manager = FakeWindowManager(":1")
    manifest = capture_session(
        tmp_path,
        test_ghostty_tabs=True,
        environment_loader=lambda: {"DISPLAY": ":1"},
        window_loader=lambda: [],
        desktop_grabber=fake_desktop_png,
        window_grabber=fake_window_png,
        manager_factory=lambda _display_name: manager,
    )
    assert manifest["ghostty_tab_test"] == "skipped_no_window"
    assert manager.shortcuts == []
```

- [ ] **Step 4: Run tests RED.**

```bash
PYTHONNOUSERSITE=1 pytest -q .agents/skills/ai-station-gui/test/test_ai_station_capture.py
```

Expected: current `choose_window` raises when either optional window is absent and the old manifest lacks optional/null fields.

- [ ] **Step 5: Implement desktop-first optional selection.**

Split `choose_window` into:

```python
def find_window(
    windows: list[dict[str, int | str]], patterns: tuple[str, ...]
) -> dict[str, int | str] | None:
    matches = [window for window in windows
               if any(pattern in str(window["description"]).lower()
                      for pattern in patterns)]
    return max(matches, key=lambda window: int(window["width"]) * int(window["height"])) \
        if matches else None
```

Capture the full desktop before optional window work. Initialize `rviz` and `ghostty` to `None`; append names to `captured_windows` or `missing_windows`. Create/open `X11WindowManager` only when a selected window needs raising/focus or Ghostty tabs are actually tested.

- [ ] **Step 6: Make output atomic and fresh.**

Create a unique timestamp plus collision-resistant suffix under `--output-root`. Refuse to overwrite an existing capture directory. Save each PNG to a temporary sibling and `Path.replace()` only after a nonzero file exists. Print exactly one JSON object to stdout; diagnostics go to stderr.

- [ ] **Step 7: Run GREEN and commit.**

```bash
PYTHONNOUSERSITE=1 pytest -q .agents/skills/ai-station-gui/test/test_ai_station_capture.py
git add .agents/skills/ai-station-gui
git commit -m "feat: capture desktop when optional GUI windows are absent"
```

---

### Task 3: Build a Safe Local-or-Remote Capture Wrapper

**Files:**
- Create from parent-repo source: `.agents/skills/ai-station-gui/scripts/capture-ai-station.sh`
- Create: `.agents/skills/ai-station-gui/test/test_capture_wrapper.py`
- Modify: `.agents/skills/ai-station-gui/references/capture-contract.md`

**Interfaces:**
- Consumes: helper JSON manifest.
- Produces: local evidence directory containing `manifest.json`, required desktop, and only declared optional artifacts.

- [ ] **Step 1: Transfer the existing wrapper as migration input.**

From the Mac/orchestrator:

```bash
scp /Users/matianyi/Projects/robot_demo_001/scripts/capture-ai-station.sh \
  ai-station:/data/work/ws_moveit/.worktrees/so101-teleop-extraction/.agents/skills/ai-station-gui/scripts/capture-ai-station.sh
```

- [ ] **Step 2: Write RED wrapper tests using fake helper/SSH/SCP commands.**

Tests invoke Bash in a temporary directory and verify:

- direct-ai-station mode invokes the colocated Python helper and never invokes fake `ssh`/`scp`;
- remote mode honors `AI_STATION_SSH_TARGET`, installs/runs the helper remotely, and copies declared artifacts;
- null `rviz`/`ghostty` paths produce `RViz: not present` / `Ghostty: not present` and no SCP call;
- an invalid manifest or a missing declared desktop is nonzero;
- an output directory supplied with `--output-root` is outside the source tree and receives `manifest.json`.

The fake manifest for the no-window case is:

```python
manifest = {
    "captured_at": "2026-08-11T12-00-00",
    "desktop": "/tmp/remote/desktop.png",
    "rviz": None,
    "ghostty": None,
    "captured_windows": [],
    "missing_windows": ["rviz", "ghostty"],
    "capture_mode": "desktop_only",
    "ghostty_tab_test": "not_requested",
}
```

- [ ] **Step 3: Run wrapper tests RED.**

```bash
PYTHONNOUSERSITE=1 pytest -q .agents/skills/ai-station-gui/test/test_capture_wrapper.py
```

Expected: old wrapper always SSHes and always SCPs RViz/Ghostty paths.

- [ ] **Step 4: Implement explicit execution-mode detection.**

The wrapper locates its helper relative to itself. Mode selection order:

1. `--local` forces direct execution and rejects `--remote`.
2. `--remote` forces SSH and rejects `--local`.
3. Otherwise, `/data/work/ws_moveit` plus the ai-station hostname/workspace check chooses local; all other hosts choose remote.

In local mode, execute:

```bash
python3 "$SCRIPT_DIR/ai-station-capture.py" --output-root "$evidence_root"
```

Never call SSH in this branch.

- [ ] **Step 5: Validate and transfer only declared paths.**

Use Python JSON parsing to validate required keys and that `desktop` is a nonempty string. For each optional field, copy only if it is a nonempty string. Write the exact manifest into the evidence directory. Never use an old destination as success evidence; fail if the current desktop was not freshly created.

- [ ] **Step 6: Run GREEN and commit.**

```bash
PYTHONNOUSERSITE=1 pytest -q .agents/skills/ai-station-gui/test/test_capture_wrapper.py
bash -n .agents/skills/ai-station-gui/scripts/capture-ai-station.sh
git add .agents/skills/ai-station-gui
git commit -m "feat: add local and remote ai-station capture fallback"
```

---

### Task 4: Route Current moveit-demo Skills and Docs to the New Owner

**Files:**
- Modify: `.agents/skills/so101-dev/references/ai-station-access.md`
- Modify: `.agents/skills/so101-dev/references/test-and-acceptance.md`
- Modify: `.agents/skills/gazebo-video-debug/SKILL.md`
- Modify: `AGENTS.md` only if its current GUI section needs a direct Skill pointer
- Modify: current operator README/docs discovered by targeted `rg`
- Modify: `.agents/skills/ai-station-gui/test/test_skill_contract.py`

**Interfaces:**
- Produces: one current screenshot workflow and the new tiler command `ros2 run so101_teleop tile_ai_station_guis.py`.

- [ ] **Step 1: Add RED documentation-link assertions.**

Assert current Skills use `.agents/skills/ai-station-gui/` and no longer direct users to the root repository `scripts/capture-ai-station.sh`. Assert current tiler commands use `so101_teleop`.

- [ ] **Step 2: Update routing text without duplicating the Skill.**

`so101-dev` and `gazebo-video-debug` should say to invoke/read `ai-station-gui` for GUI screenshot/control. They may retain SO-101 evidence requirements but must not copy the capture implementation or a second capability router.

Replace active commands with:

```bash
ros2 run so101_teleop tile_ai_station_guis.py
.agents/skills/ai-station-gui/scripts/capture-ai-station.sh --local \
  --output-root "$capture_evidence_dir/captures"
```

Define `capture_evidence_dir` from the current run's `mktemp -d` evidence directory; do not hard-code a stale example as an acceptance artifact.

- [ ] **Step 3: Preserve historical evidence files.**

Before editing, classify `docs/superpowers/{specs,plans}`, `docs/handoffs`, and experiment ledgers as historical. Do not bulk-rewrite their old commands. Limit edits to current Skills, AGENTS, README, and active operator docs.

- [ ] **Step 4: Run contract/link checks and commit.**

```bash
PYTHONNOUSERSITE=1 pytest -q .agents/skills/ai-station-gui/test
rg -n "scripts/capture-ai-station.sh|ros2 run so101_gazebo_demo_cpp tile_ai_station_guis.py" \
  AGENTS.md README.md .agents/skills src/so101_teleop/docs
git diff --check
git add .agents AGENTS.md README.md src/so101_teleop/docs
git commit -m "docs: route ai-station GUI work through dedicated skill"
```

Expected: targeted current-surface `rg` returns no obsolete entry. Historical results may still contain old commands and are not failures.

---

### Task 5: Live No-Window and CUA-Priority Acceptance

**Files:**
- Modify only if behavior differs: `.agents/skills/ai-station-gui/references/capture-contract.md`

**Interfaces:**
- Produces: fresh live desktop evidence for the no-Ghostty/no-target-window path and recorded proof of which routing path was used.

- [ ] **Step 1: Inspect `codex-cua` without taking control.**

```bash
tmux list-sessions 2>/dev/null || true
tmux capture-pane -pt codex-cua -S -200 2>/dev/null || true
```

If it is busy, do not send keys or restart it. The script fallback can still be validated read-only.

- [ ] **Step 2: Determine live CUA availability from the current agent tools.**

Record current agent identity, the loaded `cua-driver` Skill/tool name and schema, and a health probe. If healthy, take a snapshot, perform only an approved benign view/focus action if needed, then take a fresh snapshot. If unavailable/degraded, record the fallback reason; do not claim CUA control.

- [ ] **Step 3: Validate the script in the actual absent-window condition.**

Use an evidence directory under `/tmp`, not the repository:

```bash
capture_evidence_dir=$(mktemp -d)
.agents/skills/ai-station-gui/scripts/capture-ai-station.sh --local \
  --output-root "$capture_evidence_dir"
```

Do not close existing user windows to manufacture the condition. If Ghostty is naturally absent, require `ghostty: null`; if both target windows are naturally absent, require `capture_mode: desktop_only`. In every case require a fresh nonzero desktop and exit `0`.

- [ ] **Step 4: Validate `--test-ghostty-tabs` safely.**

When Ghostty is absent, rerun with `--test-ghostty-tabs`. Require `skipped_no_window`, zero injected shortcuts, and exit `0`. If Ghostty exists, do not run tab control while another user/agent owns it; stop at the unit-test evidence unless ownership is explicit.

- [ ] **Step 5: Inspect the actual desktop image and run final tests.**

Open the fresh `desktop.png` and describe what is visible; file existence alone is insufficient. Then run:

```bash
PYTHONNOUSERSITE=1 pytest -q .agents/skills/ai-station-gui/test
bash -n .agents/skills/ai-station-gui/scripts/capture-ai-station.sh
git diff --check
git status --short
```

- [ ] **Step 6: Commit only a necessary contract correction.**

If live behavior required a documentation correction:

```bash
git add .agents/skills/ai-station-gui/references/capture-contract.md
git commit -m "docs: align ai-station capture contract with live validation"
```

Otherwise do not create an empty commit.
