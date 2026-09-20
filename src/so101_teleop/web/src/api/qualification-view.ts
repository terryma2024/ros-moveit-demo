/**
 * The single read-only worker-qualification view.
 *
 * Every exact N is shown with the provider's own status. Until the budget provider is
 * integrated the view is UNKNOWN and the option stays disabled: the UI must never lower N,
 * substitute ADAPTIVE, or present demo numbers as qualification.
 */
import type { components } from "@/api/unified-schema";

export type QualificationView = components["schemas"]["QualificationViewResponse"];

export const BUDGET_PROVIDER_NOT_READY = "BUDGET_PROVIDER_NOT_READY";

export function unknownQualification(
  selected_n: number,
  runtime_identity: string,
): QualificationView {
  return {
    selected_n,
    status: "UNKNOWN",
    reasons: [BUDGET_PROVIDER_NOT_READY],
    runtime_identity,
    contract_version: 2,
    profile_sha256: null,
    approval_sha256: null,
  };
}

export type WorkerOption = { value: number; disabled: boolean; reason: string };

/** A worker selector entry. Only an AVAILABLE, promoted N is selectable. */
export function workerOption(view: QualificationView): WorkerOption {
  const reason =
    view.reasons.length > 0
      ? view.reasons.join(", ")
      : view.status === "AVAILABLE"
        ? ""
        : view.status;
  const promoted =
    view.status === "AVAILABLE" &&
    Boolean(view.profile_sha256) &&
    Boolean(view.approval_sha256);
  return { value: view.selected_n, disabled: !promoted, reason: promoted ? "" : reason };
}

/** Points stay 4..20 inclusive, with the four fixed anchors included. */
export function pointCountOptions(): number[] {
  return Array.from({ length: 17 }, (_value, index) => index + 4);
}
