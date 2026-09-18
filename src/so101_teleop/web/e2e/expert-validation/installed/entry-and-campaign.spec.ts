import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, mkdirSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { installedTest as test, expect, installPrefix, pythonExecutable, QUALIFICATION_ENV, resolvePackagePrefixes } from "../fixtures/installed";
import { readJournalEvents, storeQuery } from "../assertions/journal";
import { ExpertValidationPage } from "../pages/expert-validation-page";


async function freePort(): Promise<number> {
  return new Promise((resolvePromise, rejectPromise) => {
    const server = createServer();
    server.once("error", rejectPromise);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address === null || typeof address === "string") {
        rejectPromise(new Error("PORT_ALLOCATION_FAILED"));
        return;
      }
      server.close(() => resolvePromise(address.port));
    });
  });
}

type EntryHandle = { stop: () => Promise<number | null> };

async function startProductionEntry(evidenceRoot: string, port: number, logPath: string): Promise<EntryHandle> {
  const prefix = installPrefix();
  const prefixes = resolvePackagePrefixes(
    prefix, process.env.SO101_E2E_DEPENDENCY_PREFIX ?? "/data/work/ws_moveit/install",
  );
  const sitePackages = prefixes.map((entry) => join(entry, "lib/python3.12/site-packages"));
  const entry = join(prefix, "so101_teleop/lib/so101_teleop/so101_expert_validation_server.py");
  if (!existsSync(entry)) throw new Error(`INSTALLED_ENTRY_MISSING: ${entry}`);
  const binding = process.env.SO101_VALIDATION_PROVENANCE_BINDING;
  if (!binding) throw new Error("SO101_VALIDATION_PROVENANCE_BINDING_REQUIRED");
  const { createWriteStream } = await import("node:fs");
  const logStream = createWriteStream(logPath, { flags: "a" });
  const child: ChildProcess = spawn(pythonExecutable(), [entry], {
    env: {
      ...process.env,
      ...QUALIFICATION_ENV,
      SO101_DISABLE_KIMI_EDITABLE_FINDER: "1",
      PYTHONNOUSERSITE: "1",
      PYTHONPATH: [...sitePackages, "/opt/ros/jazzy/lib/python3.12/site-packages"].join(":"),
      AMENT_PREFIX_PATH: [...prefixes, "/opt/ros/jazzy"].join(":"),
      ROS_HOME: join(evidenceRoot, "ros-home"),
      ROS_LOG_DIR: join(evidenceRoot, "ros-home", "log"),
      SO101_VALIDATION_EVIDENCE_ROOT: evidenceRoot,
      SO101_VALIDATION_PORT: String(port),
      SO101_VALIDATION_WEB_ROOT: join(prefix, "so101_teleop/share/so101_teleop/web"),
      SO101_VALIDATION_PROVENANCE_BINDING: binding,
      SO101_VALIDATION_PARALLEL_CONFIG: join(
        prefix,
        "so101_demo_py/share/so101_demo_py/config/mujoco/parallel_batch_v2.yaml",
      ),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout?.pipe(logStream);
  child.stderr?.pipe(logStream);
  const deadline = Date.now() + 30_000;
  for (;;) {
    if (child.exitCode !== null) {
      throw new Error(`PRODUCTION_ENTRY_EXITED:${child.exitCode}`);
    }
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`);
      if (response.ok) break;
    } catch {
      // server not up yet
    }
    if (Date.now() > deadline) {
      child.kill("SIGKILL");
      throw new Error("PRODUCTION_ENTRY_READY_TIMEOUT");
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 200));
  }
  return {
    stop: async () => {
      child.kill("SIGINT");
      const stopDeadline = Date.now() + 15_000;
      while (child.exitCode === null) {
        if (Date.now() > stopDeadline) {
          child.kill("SIGKILL");
          break;
        }
        await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
      }
      return child.exitCode;
    },
  };
}

async function waitCampaignTerminal(baseURL: string, campaignId: string, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const response = await fetch(`${baseURL}/expert-validation/campaigns/${campaignId}`);
    expect(response.status).toBe(200);
    const projection = await response.json();
    if (
      ["COMPLETED", "COMPLETED_WITH_FAILURES", "INFRA_FAILED", "CANCELLED"].includes(projection.status)
      && projection.batch_cleanup_complete === true
    ) {
      return projection;
    }
    if (Date.now() > deadline) {
      throw new Error(`CAMPAIGN_TERMINAL_TIMEOUT: ${projection.status}`);
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
  }
}

test("S01 installed production console entry serves health and page spec:default", async ({ page }, testInfo) => {
  const slug = testInfo.title.replace(/[^a-zA-Z0-9]+/g, "-").slice(0, 60);
  const root = join(
    process.env.SO101_E2E_EVIDENCE_ROOT ?? "", "server", `s01-entry-${slug}-${Date.now().toString(36)}`,
  );
  mkdirSync(join(root, "state"), { recursive: true });
  const port = await freePort();

  const first = await startProductionEntry(join(root, "state"), port, join(root, "entry-1.log"));
  let second: EntryHandle | null = null;
  try {
    const health = await fetch(`http://127.0.0.1:${port}/health`);
    expect(health.status).toBe(200);
    expect((await health.json()).service).toBe("expert-validation");

    await page.goto(`http://127.0.0.1:${port}/expert-validation`);
    await expect(page.getByRole("heading", { name: "SO-101 Expert Validation" })).toBeVisible();

    const exitCode = await first.stop();
    expect(exitCode).toBe(0);

    // The writer lock and database handle must be re-acquirable after exit.
    const secondPort = await freePort();
    second = await startProductionEntry(join(root, "state"), secondPort, join(root, "entry-2.log"));
    const healthAfter = await fetch(`http://127.0.0.1:${secondPort}/health`);
    expect(healthAfter.status).toBe(200);
  } finally {
    await first.stop();
    if (second) await second.stop();
  }
});

test("S02 Chrome campaign flow matches the durable helper journal spec:default", async ({ page, installedServer, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(4);
  await app.configureSequential();
  await app.runPreflight();
  await app.startValidation();

  const campaigns = await (await fetch(`${installedServer.baseURL}/expert-validation/campaigns`)).json();
  expect(campaigns).toHaveLength(1);
  const campaignId = campaigns[0].campaign_id;
  const terminal = await waitCampaignTerminal(installedServer.baseURL, campaignId);
  expect(terminal.status).toBe("COMPLETED_WITH_FAILURES");
  expect(terminal.execution_mode).toBe("SEQUENTIAL");
  expect(terminal.points).toHaveLength(4);
  for (const point of terminal.points) {
    expect(point.status).toBe("FAILED");
    expect(point.retry_eligible).toBe(true);
    expect(point.artifacts.length).toBeGreaterThan(0);
    expect(point.artifact_ids).not.toContain("");
  }

  const manifest = await (
    await fetch(`${installedServer.baseURL}/expert-validation/manifests/${terminal.manifest_id}`)
  ).json();
  const manifestPointIds = manifest.points.map((point: { id: string }) => point.id).sort();

  const journalRoot = join(
    installedServer.serverRoot, "campaigns", campaignId, terminal.batch_id, "coordinator",
  );
  const events = readJournalEvents(journalRoot);
  const started = events.filter((event) => event.type === "BATCH_STARTED");
  expect(started).toHaveLength(1);
  const batch = started[0].payload.batch as Record<string, unknown>;
  expect(batch.batch_id).toBe(terminal.batch_id);
  expect(batch.campaign_id).toBe(campaignId);
  expect(batch.worker_count).toBe(1);
  expect(batch).not.toHaveProperty("max_points_per_worker");
  expect(batch.run_mode).toBe("execute");
  expect([...(batch.point_ids as string[])].sort()).toEqual(manifestPointIds);
  expect(events.filter((event) => event.type === "RESULT_COMMITTED")).toHaveLength(4);
  expect(events.some((event) => event.type === "BATCH_TERMINAL")).toBe(true);

  const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
  const rows = storeQuery(
    pythonExecutable(), database,
    "SELECT campaign_id, execution_mode FROM campaigns",
  ) as Array<Record<string, unknown>>;
  expect(rows).toHaveLength(1);
  expect(rows[0].campaign_id).toBe(campaignId);
  expect(consoleErrors).toEqual([]);
});

test("S03 a second Chrome context stays fenced out spec:default", async ({ page, browser, installedServer }) => {
  const appA = new ExpertValidationPage(page);
  await appA.goto();
  await appA.acquireLease();

  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();
  const appB = new ExpertValidationPage(pageB);
  try {
    await appB.goto();
    await pageB.getByRole("button", { name: "Acquire lease" }).click();
    await expect(pageB.getByText("LEASE_ALREADY_HELD")).toBeVisible();
    await expect(appB.startButton()).toBeDisabled();

    const forged = await pageB.request.post(`${installedServer.baseURL}/expert-validation/campaigns/preflight`, {
      data: {
        service_session_id: "session-b",
        lease_id: "lease-b",
        lease_generation: 1,
        manifest_id: "manifest-b",
        contract_version: 2,
        execution_mode: "SEQUENTIAL",
        worker_count: 1,
      },
    });
    expect(forged.status()).toBe(409);
  } finally {
    await contextB.close();
  }

  // The fenced-out session caused zero execution spawns.
  const campaignsDir = join(installedServer.serverRoot, "campaigns");
  expect(existsSync(campaignsDir) ? readdirSync(campaignsDir) : []).toEqual([]);
});

test("S04 browser reconnect restores the same running campaign spec:slow", async ({ page, installedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(4);
  await app.configureSequential();
  await app.runPreflight();
  await app.startValidation();

  const campaigns = await (await fetch(`${installedServer.baseURL}/expert-validation/campaigns`)).json();
  expect(campaigns).toHaveLength(1);
  const campaignId = campaigns[0].campaign_id;

  const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
  const ownersBefore = storeQuery(
    pythonExecutable(), database,
    "SELECT batch_id, pid FROM owned_execution",
  ) as Array<Record<string, unknown>>;
  expect(ownersBefore).toHaveLength(1);

  // Disconnect and reopen the browser page inside the lease TTL.
  await page.close();
  const reopened = await page.context().newPage();
  const restored = new ExpertValidationPage(reopened);
  await restored.goto();
  await expect(
    reopened.getByRole("heading", { name: new RegExp(`^Campaign ${campaignId}`) }),
  ).toBeVisible({ timeout: 15_000 });

  const campaignsAfter = await (
    await fetch(`${installedServer.baseURL}/expert-validation/campaigns`)
  ).json();
  expect(campaignsAfter).toHaveLength(1);
  expect(campaignsAfter[0].campaign_id).toBe(campaignId);
  const ownersAfter = storeQuery(
    pythonExecutable(), database,
    "SELECT batch_id, pid FROM owned_execution",
  ) as Array<Record<string, unknown>>;
  expect(ownersAfter).toEqual(ownersBefore);

  await waitCampaignTerminal(installedServer.baseURL, campaignId);
});
