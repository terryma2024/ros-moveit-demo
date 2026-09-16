import { join } from "node:path";

import { installedTest as test, expect, pythonExecutable } from "../fixtures/installed";
import { storeQuery } from "../assertions/journal";
import { ExpertValidationPage } from "../pages/expert-validation-page";
import {
  api, acquireLease, createManifest, fixedConfig, preflight, startCampaign, waitStatus,
} from "./support";

const OPAQUE_ID = /^[0-9a-f]{32}$/;

test("S08 the page views only opaque registered artifacts of the campaign spec:default", async ({ page, installedServer, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(4);
  await app.configureSequential();
  await app.runPreflight();
  await app.startValidation();

  const client = api(installedServer.baseURL);
  const campaigns = await client.get("/expert-validation/campaigns");
  const campaignId = campaigns.body[0].campaign_id;
  const terminal = await waitStatus(
    client, campaignId,
    (value) => value.status === "COMPLETED_WITH_FAILURES" && value.batch_cleanup_complete === true,
  );

  // Every projected artifact id is opaque and resolvable over HTTP.
  const artifactIds: string[] = terminal.points.flatMap(
    (point: any) => point.artifacts.map((artifact: any) => artifact.artifact_id),
  );
  expect(artifactIds.length).toBeGreaterThan(0);
  for (const artifactId of artifactIds) {
    expect(artifactId).toMatch(OPAQUE_ID);
    const response = await client.get(`/expert-validation/artifacts/${artifactId}`);
    expect(response.status).toBe(200);
  }

  // The evidence panel renders the same opaque URLs for a selected point.
  await app.selectPoint("P01");
  const evidence = app.evidenceSection("P01");
  await expect(evidence.getByRole("img").first()).toBeVisible();
  const sources = await evidence.locator("img").evaluateAll(
    (nodes) => nodes.map((node) => (node as HTMLImageElement).getAttribute("src") ?? ""),
  );
  expect(sources.length).toBeGreaterThan(0);
  for (const source of sources) {
    expect(source).toMatch(/^\/expert-validation\/artifacts\/[0-9a-f]{32}$/);
  }
  const links = await evidence.locator("a").evaluateAll(
    (nodes) => nodes.map((node) => (node as HTMLAnchorElement).getAttribute("href") ?? ""),
  );
  for (const link of links) {
    expect(link).toMatch(/^\/expert-validation\/artifacts\/[0-9a-f]{32}$/);
  }

  // A stale artifact id from another server instance does not resolve here.
  const stale = await client.get(`/expert-validation/artifacts/${"0".repeat(32)}`);
  expect(stale.status).toBe(404);
  expect(consoleErrors).toEqual([]);
});

for (const mode of ["identity", "sha256", "escape", "symlink"] as const) {
  test(`S08 tampered helper evidence (${mode}) never registers @api-contract spec:tamper-${mode}`, async ({ installedServer }) => {
    const client = api(installedServer.baseURL);
    const session = `s08-${mode}`;
    const lease = await acquireLease(client, session);
    const manifest = await createManifest(client, 4);
    const config = fixedConfig(lease, session, manifest.manifest_id);
    const campaignId = await startCampaign(
      client, config, `s08-start-${mode}`, await preflight(client, config),
    );

    // The projection must fail closed once the journal references bad evidence.
    await expect
      .poll(async () => {
        const response = await client.get(`/expert-validation/campaigns/${campaignId}`);
        return response.status === 409 ? response.body.code : response.status;
      }, { timeout: 30_000 })
      .toBe("UPSTREAM_PROJECTION_INVALID");

    // Nothing was registered: no opaque id exists for this server.
    const guess = await client.get(`/expert-validation/artifacts/${"1".repeat(32)}`);
    expect(guess.status).toBe(404);

    // Zero new execution spawns beyond the tampered batch.
    const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
    const owners = storeQuery(
      pythonExecutable(), database, "SELECT batch_id FROM owned_execution",
    ) as Array<Record<string, unknown>>;
    expect(owners).toHaveLength(1);
  });
}
