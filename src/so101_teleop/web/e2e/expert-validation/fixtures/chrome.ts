import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export type ChromeProvenance = {
  executablePath: string;
  version: string;
};

export function chromeExecutablePath(): string {
  const override = process.env.SO101_PLAYWRIGHT_CHROME;
  if (override) return override;
  return process.platform === "darwin"
    ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    : "/usr/bin/google-chrome";
}

export function proveChrome(caseEvidenceDir: string): ChromeProvenance {
  const executablePath = chromeExecutablePath();
  if (!existsSync(executablePath)) {
    throw new Error(`CHROME_EXECUTABLE_MISSING: ${executablePath}`);
  }
  const version = execFileSync(executablePath, ["--version"], { encoding: "utf-8" }).trim();
  if (!/Google Chrome \d/.test(version)) {
    throw new Error(`CHROME_NOT_OFFICIAL: ${version}`);
  }
  mkdirSync(caseEvidenceDir, { recursive: true });
  writeFileSync(
    join(caseEvidenceDir, "chrome.json"),
    JSON.stringify({ executablePath, version }, null, 2) + "\n",
  );
  return { executablePath, version };
}

export function e2eEvidenceRoot(): string {
  const root = process.env.SO101_E2E_EVIDENCE_ROOT;
  if (!root || !root.startsWith("/")) {
    throw new Error("SO101_E2E_EVIDENCE_ROOT_REQUIRED");
  }
  return root;
}
