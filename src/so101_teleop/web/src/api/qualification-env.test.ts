/**
 * The installed gate's qualification environment, platform bound.
 *
 * The installed fixtures spawn the production server themselves and hand it this environment, so a
 * value here overrides the ambient one. Every model and acceptance path in it was ai-station's
 * `/data/work` tree, which no other host has: on macOS the server refused to start with
 * `SO101_VALIDATION_YOLO_WEIGHTS_INVALID` and all twenty-five installed specs failed in 630 ms each.
 * The rule is the same one the durable-root fixture already follows - a platform-bound host supplies
 * its own locations, and an ai-station path is never asserted where that tree cannot exist.
 */

import { describe, expect, it } from "vitest";

import {
  AI_STATION_MODEL_PATHS,
  HOST_INDEPENDENT_QUALIFICATION,
  qualificationEnvironment,
} from "../../e2e/expert-validation/fixtures/qualification-env";

const MODEL_KEYS = [
  "SO101_VALIDATION_YOLO_WEIGHTS",
  "SO101_VALIDATION_GROUNDED_ROOT",
] as const;

/** Documents from one qualification run: the product reads them only when they are supplied. */
const RUN_EVIDENCE_KEYS = [
  "SO101_VALIDATION_PARALLEL_ACCEPTANCE",
  "SO101_VALIDATION_ADAPTIVE_ACCEPTANCE",
  "SO101_VALIDATION_ADAPTIVE_FAULT_INJECTION",
] as const;

describe("installed qualification environment", () => {
  it("asserts no ai-station path on darwin", () => {
    const env = qualificationEnvironment({ platform: "darwin", environment: {} });
    const aiStation = Object.entries(env).filter(([, value]) => value.startsWith("/data/"));
    expect(aiStation, "darwin must not carry an ai-station path").toEqual([]);
    for (const key of MODEL_KEYS) {
      expect(env[key], `${key} has no darwin default`).toBeUndefined();
    }
  });

  it("never asserts a past run's evidence document on any platform", () => {
    // The three acceptance documents are optional to the product and name one specific
    // qualification run. ai-station does not hold the files the old defaults named, so a host that
    // does not supply them must be sent none rather than a path that cannot exist.
    for (const platform of ["linux", "darwin"] as const) {
      const env = qualificationEnvironment({ platform, environment: {} });
      for (const key of RUN_EVIDENCE_KEYS) {
        expect(env[key], `${platform}: ${key}`).toBeUndefined();
      }
    }
  });

  it("takes the darwin locations from the environment it is given", () => {
    const env = qualificationEnvironment({
      platform: "darwin",
      environment: {
        SO101_VALIDATION_YOLO_WEIGHTS: "/private/tmp/models/yolo/best.pt",
        SO101_VALIDATION_GROUNDED_ROOT: "/private/tmp/models/grounded",
      },
    });
    expect(env.SO101_VALIDATION_YOLO_WEIGHTS).toBe("/private/tmp/models/yolo/best.pt");
    expect(env.SO101_VALIDATION_GROUNDED_ROOT).toBe("/private/tmp/models/grounded");
  });

  it("keeps the ai-station defaults on linux", () => {
    const env = qualificationEnvironment({ platform: "linux", environment: {} });
    for (const key of MODEL_KEYS) {
      expect(env[key], `${key} keeps its ai-station default`).toBe(
        AI_STATION_MODEL_PATHS[key as keyof typeof AI_STATION_MODEL_PATHS],
      );
    }
  });

  it("lets the ambient environment win on either platform", () => {
    for (const platform of ["linux", "darwin"] as const) {
      const env = qualificationEnvironment({
        platform,
        environment: { SO101_VALIDATION_YOLO_WEIGHTS: "/somewhere/else/best.pt" },
      });
      expect(env.SO101_VALIDATION_YOLO_WEIGHTS, platform).toBe("/somewhere/else/best.pt");
    }
  });

  it("keeps the host-independent entries unchanged on both platforms", () => {
    for (const platform of ["linux", "darwin"] as const) {
      const env = qualificationEnvironment({ platform, environment: {} });
      expect(env.SO101_VALIDATION_BROKER_IMAGE, platform).toBe(
        HOST_INDEPENDENT_QUALIFICATION.SO101_VALIDATION_BROKER_IMAGE,
      );
      expect(env.SO101_VALIDATION_ADAPTIVE_PERFORMANCE_TIERS, platform).toBe(
        HOST_INDEPENDENT_QUALIFICATION.SO101_VALIDATION_ADAPTIVE_PERFORMANCE_TIERS,
      );
    }
  });

  it("defaults to this host when no platform is injected", () => {
    const env = qualificationEnvironment({ environment: {} });
    const expected =
      process.platform === "darwin" ? undefined : AI_STATION_MODEL_PATHS.SO101_VALIDATION_YOLO_WEIGHTS;
    expect(env.SO101_VALIDATION_YOLO_WEIGHTS).toBe(expected);
  });
});
