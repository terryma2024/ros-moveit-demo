import { validateLiveSimPreconditions } from "./live-sim";

/**
 * Playwright global setup for the live-sim project.  Runs before any test
 * file loads or any server/stack may spawn; throws LiveSimGateError (fail
 * closed) unless every L3 precondition holds.
 */
export default function liveSimGlobalSetup(): void {
  validateLiveSimPreconditions();
}
