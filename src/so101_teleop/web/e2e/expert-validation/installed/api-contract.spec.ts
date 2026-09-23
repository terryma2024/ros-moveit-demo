import { createHash } from "node:crypto";
import { existsSync, readdirSync } from "node:fs";
import { request as httpRequest } from "node:http";
import { join } from "node:path";

import { installedTest as test, expect, pythonExecutable } from "../fixtures/installed";
import { storeQuery } from "../assertions/journal";
import {
  api, acquireLease, createManifest, fixedConfig, preflight, startCampaign, waitStatus,
} from "./support";

function canonicalDigest(body: Record<string, unknown>): string {
  const canonical = JSON.stringify(
    Object.fromEntries(Object.entries(body).sort(([a], [b]) => (a < b ? -1 : 1))),
  );
  return createHash("sha256").update(canonical, "utf-8").digest("hex");
}

test("API rejects wrong sessions and stale fencing @api-contract spec:default", async ({ installedServer }) => {
  const client = api(installedServer.baseURL);
  const lease = await acquireLease(client, "api-session-a");
  const manifest = await createManifest(client, 4);
  const config = fixedConfig(lease, "api-session-a", manifest.manifest_id);

  const wrongSession = await client.post("/expert-validation/campaigns/preflight", {
    ...config,
    service_session_id: "api-session-b",
  });
  expect(wrongSession.status).toBe(409);
  expect(wrongSession.body.code).toBe("LEASE_IDENTITY_MISMATCH");

  const renewed = await client.put(`/expert-validation/lease/${lease.lease_id}`, {
    service_session_id: "api-session-a",
    generation: lease.generation,
  });
  expect(renewed.status).toBe(200);

  const staleGeneration = await client.post("/expert-validation/campaigns/preflight", config);
  expect(staleGeneration.status).toBe(409);
  expect(staleGeneration.body.code).toBe("STALE_LEASE_GENERATION");

  const released = await client.del(`/expert-validation/lease/${lease.lease_id}`, {
    service_session_id: "api-session-a",
    generation: renewed.body.generation,
  });
  expect(released.status).toBe(200);
  const afterRelease = await client.post("/expert-validation/campaigns/preflight", {
    ...config,
    lease_generation: renewed.body.generation,
  });
  expect(afterRelease.status).toBe(409);
  expect(afterRelease.body.code).toBe("LEASE_NOT_ACTIVE");

  // Zero business side effects from every rejection.
  const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
  expect(storeQuery(pythonExecutable(), database, "SELECT campaign_id FROM campaigns")).toEqual([]);
  expect(storeQuery(pythonExecutable(), database, "SELECT batch_id FROM owned_execution")).toEqual([]);
  const campaignsDir = join(installedServer.serverRoot, "campaigns");
  expect(existsSync(campaignsDir) ? readdirSync(campaignsDir) : []).toEqual([]);
});

test("API command ids: replay, conflict reuse, outcome unknown @api-contract spec:default", async ({ installedServer }) => {
  const client = api(installedServer.baseURL);
  const session = "api-session-cmd";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const config = fixedConfig(lease, session, manifest.manifest_id);
  const receiptId = await preflight(client, config);
  const startBody = { ...config, command_id: "api-start-1", preflight_receipt_id: receiptId };

  const first = await client.post("/expert-validation/campaigns", startBody);
  expect(
    first.status,
    `start: sent ${JSON.stringify(startBody)} -> ${JSON.stringify(first.body)}`,
  ).toBe(200);
  const replay = await client.post("/expert-validation/campaigns", startBody);
  expect(replay.status).toBe(200);
  expect(replay.body.campaign_id).toBe(first.body.campaign_id);

  const otherManifest = await createManifest(client, 4);
  const conflict = await client.post("/expert-validation/campaigns", {
    ...startBody,
    manifest_id: otherManifest.manifest_id,
  });
  expect(conflict.status).toBe(409);
  expect(conflict.body.code).toBe("COMMAND_ID_REUSED");

  // A durably begun command without a committed outcome is outcome-unknown.
  const unknownBody = { ...startBody, command_id: "api-start-unknown" };
  const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
  const digest = canonicalDigest(unknownBody);
  const insert = await import("node:child_process");
  insert.execFileSync(
    pythonExecutable(),
    [
      "-c",
      "import sqlite3, sys\n"
        + "c = sqlite3.connect(sys.argv[1])\n"
        + "c.execute(\"INSERT INTO commands VALUES (?, ?, 'START_CAMPAIGN', 'IN_PROGRESS', NULL)\", (sys.argv[2], sys.argv[3]))\n"
        + "c.commit()\n",
      database,
      "api-start-unknown",
      digest,
    ],
  );
  const unknown = await client.post("/expert-validation/campaigns", unknownBody);
  expect(unknown.status).toBe(409);
  expect(unknown.body.code).toBe("COMMAND_OUTCOME_UNKNOWN");

  const campaigns = await client.get("/expert-validation/campaigns");
  expect(campaigns.body).toHaveLength(1);
  await waitStatus(
    client, first.body.campaign_id,
    (value) => value.status === "COMPLETED_WITH_FAILURES" && value.batch_cleanup_complete === true,
  );
});

function rawGet(port: number, path: string): Promise<{ status: number; body: string }> {
  // Raw sockets: no client-side URL normalization of dot segments.
  return new Promise((resolvePromise, rejectPromise) => {
    const request = httpRequest(
      { host: "127.0.0.1", port, path, method: "GET" },
      (response) => {
        const chunks: Buffer[] = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => resolvePromise({
          status: response.statusCode ?? 0,
          body: Buffer.concat(chunks).toString("utf-8"),
        }));
      },
    );
    request.on("error", rejectPromise);
    request.end();
  });
}

test("API artifact route rejects forged and encoded ids @api-contract spec:default", async ({ installedServer }) => {
  const client = api(installedServer.baseURL);
  const forged = [
    "0".repeat(32),
    "..",
    "../..",
    "..%2F..%2Fetc%2Fpasswd",
    "%2e%2e%2f%2e%2e",
    "a/b",
    "a%2Fb",
    "x".repeat(4096),
    "not-hex-at-all",
    "%00",
  ];
  for (const id of forged) {
    const response = await rawGet(
      installedServer.port, `/expert-validation/artifacts/${id}`,
    );
    expect(response.status).toBe(404);
    expect(response.body).not.toContain(installedServer.serverRoot);
    expect(response.body).not.toContain("/data/work");
  }

  const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
  expect(storeQuery(pythonExecutable(), database, "SELECT campaign_id FROM campaigns")).toEqual([]);
  expect(storeQuery(pythonExecutable(), database, "SELECT batch_id FROM owned_execution")).toEqual([]);
});
