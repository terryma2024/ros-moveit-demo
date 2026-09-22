"""Live-fixture contract tests (offline): the gates that authorize a real run.

These are source-backed structural checks. They do not run a live simulation and they do
not claim any live acceptance.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE = Path(__file__).parents[2]
FIXTURE = PACKAGE / "web/e2e/expert-validation/fixtures/live-sim.ts"
DURABLE_ROOT = PACKAGE / "web/e2e/expert-validation/fixtures/durable-root.ts"
GLOBAL_SETUP = PACKAGE / "web/e2e/expert-validation/fixtures/live-sim-global-setup.ts"
LIVE_CONFIG = PACKAGE / "web/playwright.live-sim.config.ts"


def test_live_fixture_targets_one_unified_launcher_and_keeps_its_gates():
    fixture = FIXTURE.read_text()
    assert "so101_unified_web_server.py" in fixture
    assert "so101_expert_validation_server.py" not in fixture, (
        "the live fixture must not start the deprecated per-domain listener"
    )
    assert "SO101_UNIFIED_LIVE_AUTHORIZATION" in fixture
    assert "requireGate" in fixture
    assert "SO101_ENABLE_LIVE_SIM_E2E" in fixture
    assert "SO101_E2E_INSTALL_PREFIX" in fixture
    assert "LIVE_SIM_STACK_PRESENT" in fixture


def test_live_authorization_is_required_and_cannot_carry_proofs():
    fixture = FIXTURE.read_text()
    assert "requireUnifiedLiveAuthorization(env)" in fixture, (
        "the opt-in flag alone must never authorize a live run"
    )
    for code in (
        "LIVE_SIM_UNIFIED_AUTHORIZATION_REQUIRED",
        "LIVE_SIM_AUTHORIZATION_EXPIRED",
        "LIVE_SIM_AUTHORIZATION_SCOPE_MISMATCH",
        "LIVE_SIM_AUTHORIZATION_MUST_NOT_CARRY_PROOFS",
        "LIVE_SIM_AUTHORIZATION_RUNTIME_IDENTITIES_REQUIRED",
    ):
        assert code in fixture, code


def test_global_setup_reads_the_authorization_before_any_spawn():
    setup = GLOBAL_SETUP.read_text()
    assert "live-sim" in setup or "validateLiveSimPreconditions" in setup
    fixture = FIXTURE.read_text()
    authorize_at = fixture.index("requireUnifiedLiveAuthorization(env)")
    stack_at = fixture.index("stackConflicts(deps.stackScan)")
    assert authorize_at < stack_at, "authorization must be checked before stack inspection"


def test_the_durable_root_rule_is_platform_bound_and_still_fails_closed():
    """ai-station keeps the registered /data/work/so101-evidence tree; macOS has no /data at all
    (its root is a sealed, read-only system volume), so the registered root there is the task's own
    ``SO101_TASK_ROOT`` and the run must be a private directory inside it. The macOS branch is a
    narrow portability rule, never a fallback: a relative root, an unregistered root, a symlink or a
    world-readable directory is refused by name.
    """

    fixture = FIXTURE.read_text()
    rule = DURABLE_ROOT.read_text()
    assert "durableRootFailure" in fixture, "the live gate must use the shared durable-root rule"
    assert "SO101_TASK_ROOT" in rule
    # The ai-station prefix stays in force for every other platform, next to the darwin branch.
    assert "/data/work/so101-evidence/" in rule
    assert 'platform !== "darwin"' in rule, "the ai-station prefix must remain the non-darwin rule"
    assert "isSymbolicLink" in rule and "0o077" in rule, (
        "the darwin branch must refuse symlinks and world-readable run roots"
    )
    for code in (
        "LIVE_SIM_EVIDENCE_ROOT_REQUIRED",
        "LIVE_SIM_EVIDENCE_ROOT_NOT_PRIVATE",
        "LIVE_SIM_SERVICE_STATE_ROOT_REQUIRED",
        "LIVE_SIM_SERVICE_STATE_ROOT_INVALID",
        "LIVE_SIM_SERVICE_STATE_ROOT_NOT_PRIVATE",
    ):
        assert code in fixture, code


def test_live_config_keeps_the_reviewed_projects_and_adds_the_unified_one():
    """The plan named four projects (sequential/parallel/adaptive/unified). The reviewed
    suite on this branch has eight, owned by the parallel-budget task. Renaming or removing
    them would break another task's live workflow, so the unified project is added and the
    existing names are kept; the producer dependency is the reviewed ``r01-sequential``.
    """
    config = LIVE_CONFIG.read_text()
    for project in (
        "live-preflight",
        "r01-sequential",
        "parallel-resource",
        "adaptive",
        "unified",
    ):
        assert f'name: "{project}"' in config, project
    unified = config.split('name: "unified"')[1]
    assert "unified/live-sim.spec.ts" in unified
    assert 'dependencies: ["r01-sequential"]' in unified
    assert "01-sequential.spec.ts" in config
    assert "02-parallel.spec.ts" in config or "02-parallel|04-start-guard" in config
    assert "03-adaptive.spec.ts" in config


def test_unified_live_spec_exists_and_uses_the_shared_fixture():
    spec = (PACKAGE / "web/e2e/unified/live-sim.spec.ts").read_text()
    assert "liveSimTest" in spec
    assert "expert-validation/fixtures/live-sim" in spec
    assert "CONTROLLER_INSTANCE_REQUIRED" in spec
    assert "/health/ready" in spec


def test_unified_live_spec_checks_the_two_required_viewports():
    spec = (PACKAGE / "web/e2e/unified/live-sim.spec.ts").read_text()
    # The two viewports the design requires must be measured in a real browser, not jsdom.
    assert "width: 1400, height: 900" in spec
    assert "width: 390, height: 844" in spec
    assert "setViewportSize" in spec
    assert "scrollWidth" in spec and "clientWidth" in spec
    assert "circle[data-point-status]" in spec


def test_provenance_binding_is_not_reintroduced_as_runtime_authority():
    """The plan asked for SO101_VALIDATION_PROVENANCE_BINDING; a later reviewed change
    removed provenance bindings from runtime authority. The reviewed behavior wins, and
    this test pins that decision so the fixture cannot silently regress either way.
    """
    fixture = FIXTURE.read_text()
    assert "SO101_VALIDATION_PROVENANCE_BINDING" not in fixture
    assert "retired provenance binding" in fixture


def test_the_published_bundle_ships_self_hosted_fonts_and_tokens():
    """The installed artifact, not just the sources: a font that never reaches `dist/fonts` would make
    every `@font-face` URL 404 in production, and a theme that never reaches the stylesheet would
    silently drop the captured design system."""
    import re

    web = PACKAGE / "web"
    dist = web / "dist"
    if not (dist / "index.html").is_file():
        import pytest

        pytest.skip("the web bundle has not been built in this checkout")

    shipped = {path.name for path in (dist / "fonts").glob("*.woff2")}
    assert {"dm-sans-variable.woff2", "outfit-variable.woff2"} <= shipped, sorted(shipped)
    assert (dist / "fonts/LICENSES.txt").is_file(), "licences must ship with the fonts"

    stylesheets = list((dist / "assets").glob("*.css"))
    assert stylesheets, "no stylesheet in the bundle"
    css = "\n".join(path.read_text() for path in stylesheets)
    for reference in ("fonts/dm-sans-variable.woff2", "fonts/outfit-variable.woff2"):
        assert reference in css, reference
    # The tokens reach the bundle too, including the independent success colour.
    assert re.search(r"--(primary|background)\s*:", css), "no design token in the built CSS"
    assert "--state-success" in css
