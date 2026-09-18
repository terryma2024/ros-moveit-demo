# Addendum: prefix metadata is DEBUG-only (2026-09-18)

**Status:** second user-authorized narrow amendment. It supersedes the instruction in
the debug-only-provenance handoff to keep installed-prefix metadata mandatory, existing,
absolute and equal, and it does not reopen anything else.

Dispatch: `7f437570-8003-4c5b-825b-f56b0db546e5`. Predecessor amendment:
`docs/superpowers/specs/2026-09-18-so101-source-commit-debug-only-amendment.md`.

## Preserved sealed bytes

No sealed design, plan, review, approval or evidence byte is rewritten or re-hashed; the
predecessor amendment lists their SHA256 values and they still hold. This file is a new
dated addendum.

## User requirement

Ament/package/installed-prefix metadata validation must not be a runtime admission rule.
Missing, relative, nonexistent, unresolvable, differing or absent prefix metadata must
never refuse execution, while genuine functional discovery of executables, launch files,
share/config/assets and package dependencies stays intact.

## Superseded clauses

1. `verify_execution_provenance` resolving `declared_installed_prefix` strictly and
   refusing `EXECUTION_INSTALLED_PREFIX_INVALID` / `EXECUTION_INSTALLED_PREFIX_MISMATCH`.
2. `resolve_installed_execution_identity` refusing `EXECUTION_PACKAGE_PREFIX_UNAVAILABLE`
   when the ament index cannot name `so101_demo_py`.
3. The CLI parse-time prefix gate and the `EXECUTION_INSTALLED_PREFIX_*` reason codes in
   `_valid_execute_context`.
4. `_has_valid_context`'s prefix-presence/absolute/agreement conditions and the
   `ExecutionProvenance.installed_prefix == DynamicRuntimeContext.installed_prefix`
   equality.
5. `RunResultManifest` refusing a missing or non-absolute installed prefix, and the
   composition/dynamic-plan manifests requiring a prefix string.

## Amended contract

* `InstalledExecutionIdentity.package_prefix`, `ExecutionProvenance.installed_prefix`,
  `DynamicRuntimeContext.installed_prefix`, `RunResultManifest.installed_prefix` and the
  composition/plan manifest inputs are `str | None`; a declared value is recorded as an
  observation, never enforced, and no placeholder is fabricated.
* No ament lookup is required for metadata: a missing index yields `None`, not a refusal.
* **Retained, functional:** `installed_executable(name)` resolves the real console script
  (ament prefix, then the share layout, then `PATH`) and raises only when the executable is
  genuinely unavailable; `get_package_share_directory` remains the functional source for
  policies, scenes and assets, so a genuinely missing ROS package or share resource is
  still a real error; the debug install manifest stays build-time only.
* **Retained, independent:** session/reset/evidence gates, control/lease/owned-scope,
  budget/execution-identity and qualified content-byte hashes, cleanup rules, and the
  fixed-profile/qualification authority. The expert-validation deployment LOCATION binding
  and the resource-budget deployment receipt checks are independent deployment gates and
  are untouched.

## Out of scope

Teleop expert-validation layout prefixes remain functional deployment locations (they name
real executables and configs) and are backed by the independent deployment receipt and
location binding; they are not debug prefix metadata. Training/benchmark artifact
identities remain unchanged.
