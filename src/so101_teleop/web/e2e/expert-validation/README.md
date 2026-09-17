# Expert Validation Chrome E2E

Three isolated Playwright layers for the SO-101 expert validation page. All
layers run the official Google Chrome binary (`/usr/bin/google-chrome` on
Linux, the macOS app path on macOS, or `SO101_PLAYWRIGHT_CHROME`); there is no
fallback to bundled Chromium.

## Layers

- `contract/*.spec.ts` (L1): Chrome against the scripted validation server.
  No ROS, no MuJoCo, no installed prefix.
- `installed/*.spec.ts` (L2): Chrome against the production service composed
  from a copied install prefix, with the typed test execution port driving
  real OS helper processes. No MuJoCo. Requires `SO101_E2E_INSTALL_PREFIX`,
  `SO101_E2E_PYTHON`, `SO101_E2E_EVIDENCE_ROOT`, and
  `SO101_VALIDATION_PROVENANCE_BINDING`.
- `live-sim/*.spec.ts` (L3): Chrome against the production entry point
  spawning the real coordinator, workers, broker, MoveIt, and MuJoCo. Runs
  serially with `workers: 1` and `retries: 0`, only after the global setup
  gate passes: `SO101_ENABLE_LIVE_SIM_E2E=1`, the registered ai-station host,
  a durable evidence root under `/data/work/so101-evidence/`, a valid
  provenance binding, and no existing stack. Any missing condition fails
  closed before anything spawns.

## Commands

```bash
bun run test:e2e            # L1 contract + legacy specs (never installed/live)
bun run test:e2e:installed  # L2 installed integration, serial
bun run test:e2e:live-sim   # L3 live acceptance; gated, opt-in only
```

The default gate ignores `installed/` and `live-sim/` by `testMatch`, not by
grep. `@api-contract` tests inside `installed/` are an adversarial HTTP
sub-suite and must collect non-zero:

```bash
bun run test:e2e:installed -- --grep @api-contract
```

## Risk boundaries

- L1/L2 green never proves robot success. L3 reports Chrome flow/projection
  and per-point robot qualification separately.
- Live runs start real simulation stacks. R01 must pass before R02 starts,
  R02 before R03; R04 is embedded in a running campaign; R05 only runs when
  the first pass ended safely with eligible business failures.
- Every layer writes evidence under the single registered evidence root:
  `browser/`, `server/`, `runtime/`, `api-contract/`, `reports/`. Tests never
  delete evidence.

## Environment on ai-station

- `TMPDIR`/`TMP`/`TEMP` for browser runs must be a short path (for example
  under `/run/user/$UID/`); Chrome's singleton socket rejects long paths.
- Pytest/colcon gates use a fresh scratch directory under the evidence root
  and prove `tempfile.gettempdir()` resolves inside it before running.
