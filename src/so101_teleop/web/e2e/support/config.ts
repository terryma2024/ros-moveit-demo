import { join } from "node:path";

export function chromeExecutablePath(): string {
  const override = process.env.SO101_PLAYWRIGHT_CHROME;
  if (override) return override;
  return process.platform === "darwin"
    ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    : "/usr/bin/google-chrome";
}

export function evidenceOutputDir(configName: string): string {
  const root = process.env.SO101_E2E_EVIDENCE_ROOT;
  if (!root || !root.startsWith("/")) return "test-results";
  return join(root, "reports", `playwright-output-${configName}`);
}

export function evidenceReportFile(configName: string): string | undefined {
  const root = process.env.SO101_E2E_EVIDENCE_ROOT;
  if (!root || !root.startsWith("/")) return undefined;
  return join(root, "reports", `playwright-${configName}.json`);
}

export const sharedUse = {
  browserName: "chromium" as const,
  launchOptions: {
    executablePath: chromeExecutablePath(),
    args: ["--no-proxy-server"],
  },
  screenshot: "only-on-failure" as const,
  trace: "retain-on-failure" as const,
};
