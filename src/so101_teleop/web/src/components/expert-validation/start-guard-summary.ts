import type { StartGuardCheck, StartGuardPolicy, StartGuardStatus } from "../../api/expert-validation-types";

const BYTES_PER_GIB = 1024 ** 3;

type Observed = number | string | null | undefined;

const numeric = (value: Observed): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const formatBytes = (value: Observed): string => {
  const number = numeric(value);
  return number === null ? "unknown" : `${(number / BYTES_PER_GIB).toFixed(1)} GiB`;
};

const formatCores = (value: Observed): string => {
  const number = numeric(value);
  return number === null ? "unknown" : `${number.toFixed(1)} cores`;
};

const formatFraction = (value: Observed): string => {
  const number = numeric(value);
  return number === null ? "unknown" : `${(number * 100).toFixed(1)}%`;
};

const describeCheck = (name: string, check: StartGuardCheck): string => {
  switch (name) {
    case "cpu_capacity":
      return `CPU ${formatCores(check.observed)} (${check.status})`;
    case "cpu_busy":
      return `CPU busy ${formatFraction(check.observed)} vs ${formatFraction(check.cutoff)} (${check.status})`;
    case "ram":
      return `RAM free ${formatBytes(check.observed)} vs floor ${formatBytes(check.cutoff)} (${check.status})`;
    case "gpu":
      return `GPU free ${formatBytes(check.observed)} vs floor ${formatBytes(check.cutoff)} (${check.status})`;
    default:
      return `${name} ${String(check.observed ?? "unknown")} ${check.unit} (${check.status})`;
  }
};

/**
 * Display-only summary of the server's startup check. It never authorizes anything: a WARN is
 * shown as a warning, a FAIL keeps its own reasons, and a missing result reads as unknown
 * rather than green.
 */
export const describeStartGuard = (
  guard: StartGuardStatus | null | undefined,
  policy?: StartGuardPolicy | null,
): string => {
  if (!guard) return "Start guard: unknown (not checked yet)";
  const parts = Object.entries(guard.checks ?? {}).map(([name, check]) => describeCheck(name, check));
  const when = typeof guard.observed_monotonic_s === "number"
    ? `checked at ${guard.observed_monotonic_s.toFixed(1)} s (monotonic)`
    : "check time unknown";
  const policyNote = policy ? `, timeout ${policy.timeout_s.toFixed(1)} s` : "";
  const cleanup = guard.cleanup_state === "CLEAR" ? "" : `, cleanup ${guard.cleanup_state}`;
  if (guard.status === "FAIL") {
    const reasons = Object.values(guard.checks ?? {})
      .filter((check) => check.status === "FAIL")
      .map((check) => check.reason)
      .join(", ");
    return `Start guard: FAIL — ${reasons || "see checks"} (${parts.join(" · ")}; ${when}${policyNote}${cleanup})`;
  }
  return `Start guard: ${guard.status} (${parts.join(" · ")}; ${when}${policyNote}${cleanup})`;
};
