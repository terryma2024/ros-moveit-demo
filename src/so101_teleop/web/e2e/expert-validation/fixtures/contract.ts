import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { test as base, expect } from "@playwright/test";

import { e2eEvidenceRoot, proveChrome } from "./chrome";

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const REPO_ROOT = resolve(PACKAGE_ROOT, "../..");
const SERVER_SCRIPT = join(PACKAGE_ROOT, "test/e2e/scripted_validation_server.py");
const SCENARIOS = join(PACKAGE_ROOT, "test/fixtures/expert_validation_e2e/scenarios");
const DIST_DIR = resolve(process.env.SO101_E2E_WEB_ROOT ?? join(PACKAGE_ROOT, "web/dist"));

function pythonExecutable(): string {
  const value = process.env.SO101_E2E_PYTHON;
  if (!value || !existsSync(value)) {
    throw new Error("SO101_E2E_PYTHON_REQUIRED");
  }
  return value;
}

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
      const { port } = address;
      server.close(() => resolvePromise(port));
    });
  });
}

export type ControlClient = {
  port: number;
  state(): Promise<Record<string, unknown>>;
  commands(): Promise<Array<Record<string, unknown>>>;
  emit(): Promise<Record<string, unknown>>;
  emitAll(): Promise<Array<Record<string, unknown>>>;
  expireLease(): Promise<void>;
  renewLease(): Promise<Record<string, unknown>>;
};

function controlClient(port: number): ControlClient {
  const base = `http://127.0.0.1:${port}`;
  const get = async (path: string) => {
    const response = await fetch(`${base}${path}`);
    if (!response.ok) throw new Error(`CONTROL_${response.status}`);
    return response.json();
  };
  const post = async (path: string) => {
    const response = await fetch(`${base}${path}`, { method: "POST" });
    if (!response.ok) throw new Error(`CONTROL_${response.status}`);
    return response.json();
  };
  return {
    port,
    state: () => get("/control/state"),
    commands: () => get("/control/commands"),
    emit: () => post("/control/emit"),
    emitAll: () => post("/control/emit-all"),
    expireLease: async () => {
      await post("/control/expire-lease");
    },
    renewLease: () => post("/control/renew-lease"),
  };
}

export type ScriptedServer = {
  port: number;
  controlPort: number;
  baseURL: string;
  control: ControlClient;
  scenarioId: string;
  scenarioSha256: string;
  evidenceDir: string;
};

type ContractFixtures = {
  scriptedServer: ScriptedServer;
  consoleErrors: string[];
};

export const contractTest = base.extend<ContractFixtures>({
  baseURL: async ({ scriptedServer }, use) => {
    await use(scriptedServer.baseURL);
  },
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const url = message.location()?.url ?? "";
      if (url.endsWith("/favicon.ico")) return;
      errors.push(`${message.text()} (${url})`);
    });
    page.on("pageerror", (error) => errors.push(String(error)));
    await use(errors);
  },
  scriptedServer: async ({ }, use, testInfo) => {
    const scenario = testInfo.title.match(/scenario:([a-z0-9-]+)/)?.[1] ?? "baseline-sequential-4";
    const evidenceDir = join(
      e2eEvidenceRoot(),
      "browser",
      "chrome-contract",
      `${testInfo.title.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 100)}-${Date.now().toString(36)}`,
    );
    mkdirSync(evidenceDir, { recursive: true });
    proveChrome(evidenceDir);
    if (!existsSync(join(DIST_DIR, "index.html"))) {
      throw new Error("WEB_ASSETS_NOT_BUILT: run `bun run build` before contract tests");
    }
    const scenarioPath = join(SCENARIOS, `${scenario}.yaml`);
    if (!existsSync(scenarioPath)) {
      throw new Error(`SCENARIO_MISSING: ${scenarioPath}`);
    }
    const port = await freePort();
    const controlPort = await freePort();
    const readyFile = join(evidenceDir, "ready.json");
    const serverLog = join(evidenceDir, "server-process.log");
    if (existsSync(readyFile)) {
      throw new Error(`STALE_READY_FILE: ${readyFile} (case evidence dir must start empty)`);
    }
    const child: ChildProcess = spawn(
      pythonExecutable(),
      [
        SERVER_SCRIPT,
        "--scenario", scenarioPath,
        "--port", String(port),
        "--control-port", String(controlPort),
        "--static-dir", DIST_DIR,
        "--evidence-dir", evidenceDir,
        "--ready-file", readyFile,
      ],
      {
        cwd: PACKAGE_ROOT,
        env: {
          ...process.env,
          PYTHONNOUSERSITE: "1",
          PYTHONPATH: [
            join(REPO_ROOT, "src/so101_demo_py/src"),
            process.env.PYTHONPATH ?? "",
          ].filter(Boolean).join(":"),
        },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    const logStream = (await import("node:fs")).createWriteStream(serverLog);
    child.stdout?.pipe(logStream);
    child.stderr?.pipe(logStream);
    const deadline = Date.now() + 15_000;
    while (!existsSync(readyFile)) {
      if (child.exitCode !== null) {
        throw new Error(`SCRIPTED_SERVER_EXITED:${child.exitCode} (see ${serverLog})`);
      }
      if (Date.now() > deadline) {
        child.kill("SIGKILL");
        throw new Error("SCRIPTED_SERVER_READY_TIMEOUT");
      }
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
    }
    const ready = JSON.parse(readFileSync(readyFile, "utf-8"));
    writeFileSync(join(evidenceDir, "server-pid.json"), JSON.stringify({ pid: ready.pid }) + "\n");
    const server: ScriptedServer = {
      port,
      controlPort,
      baseURL: `http://127.0.0.1:${port}`,
      control: controlClient(controlPort),
      scenarioId: ready.scenario_id,
      scenarioSha256: ready.scenario_sha256,
      evidenceDir,
    };
    await use(server);
    child.kill("SIGINT");
    const exitDeadline = Date.now() + 10_000;
    while (child.exitCode === null) {
      if (Date.now() > exitDeadline) {
        child.kill("SIGKILL");
        testInfo.annotations.push({ type: "server-cleanup", description: "SIGINT timeout, SIGKILL sent" });
        break;
      }
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
    }
    writeFileSync(
      join(evidenceDir, "server-exit.json"),
      JSON.stringify({ exitCode: child.exitCode, signal: child.signalCode }) + "\n",
    );
  },
});

export { expect };
