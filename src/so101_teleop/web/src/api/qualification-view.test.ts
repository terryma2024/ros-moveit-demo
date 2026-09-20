import { expect, test } from "vitest";

import {
  pointCountOptions,
  unknownQualification,
  workerOption,
  type QualificationView,
} from "./qualification-view";

test.each([2, 3, 4, 5, 6, 7, 8])("unknown N%d stays disabled before provider integration", (n) => {
  const view = unknownQualification(n, "unqualified-R");
  expect(view.status).toBe("UNKNOWN");
  expect(workerOption(view)).toEqual({ value: n, disabled: true, reason: "BUDGET_PROVIDER_NOT_READY" });
});

test("an available promoted N is the only selectable option", () => {
  const view: QualificationView = {
    selected_n: 4,
    status: "AVAILABLE",
    reasons: [],
    runtime_identity: "R",
    contract_version: 2,
    profile_sha256: "profile",
    approval_sha256: "approval",
  };
  expect(workerOption(view)).toEqual({ value: 4, disabled: false, reason: "" });
  expect(workerOption({ ...view, approval_sha256: null }).disabled).toBe(true);
  expect(workerOption({ ...view, status: "REJECTED", reasons: ["R_CHANGED"] }).disabled).toBe(true);
});

test("points stay 4..20 including the four fixed anchors", () => {
  const counts = pointCountOptions();
  expect(counts[0]).toBe(4);
  expect(counts[counts.length - 1]).toBe(20);
  expect(counts).toHaveLength(17);
});
