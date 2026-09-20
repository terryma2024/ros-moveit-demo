import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const css = readFileSync(new URL("./theme.css", import.meta.url), "utf8");
const indexCss = readFileSync(new URL("../index.css", import.meta.url), "utf8");

const rootBlock = css.slice(css.indexOf(":root {"), css.indexOf("[data-theme=\"dark\"]"));
const darkBlock = css.slice(css.indexOf("[data-theme=\"dark\"]"));

const REQUIRED = [
  "background",
  "card",
  "foreground",
  "muted",
  "border",
  "input",
  "ring",
  "primary",
  "destructive",
  "sidebar",
  "sidebar-border",
  "chart-1",
  "chart-5",
];

test("every required foundation token exists in both themes", () => {
  for (const token of REQUIRED) {
    expect(rootBlock).toContain(`--${token}:`);
    expect(darkBlock).toContain(`--${token}:`);
  }
});

test("light is the default and dark is a separate, complete set", () => {
  expect(css.indexOf(":root {")).toBeLessThan(css.indexOf('[data-theme="dark"]'));
  expect(rootBlock).toContain("--background: oklch(1 0 0)");
  expect(darkBlock).not.toContain("--background: oklch(1 0 0)");
  expect((darkBlock.match(/--[a-z0-9-]+:/g) ?? []).length).toBeGreaterThanOrEqual(31);
});

test("business outcome colours stay independent of primary", () => {
  expect(rootBlock).toContain("--state-success:");
  expect(rootBlock).toContain("--state-pending: var(--primary)");
  expect(rootBlock).toContain("--state-failure: var(--destructive)");
  expect(rootBlock).not.toMatch(/--state-success:\s*var\(--primary\)/);
});

test("display fonts carry a CJK fallback and do not need runtime font requests", () => {
  expect(rootBlock).toContain('--font-sans: "DM Sans Variable", "PingFang SC"');
  expect(rootBlock).toContain('--font-heading: "Outfit", "PingFang SC"');
  expect(css).not.toMatch(/@import\s+url\(/);
});

test("the display fonts are self-hosted, hashed and licensed", () => {
  const lock = JSON.parse(readFileSync(new URL("../../design-system.lock.json", import.meta.url), "utf8"));
  const { createHash } = require("node:crypto") as typeof import("node:crypto");
  expect(lock.fonts).toHaveLength(2);
  for (const font of lock.fonts) {
    const bytes = readFileSync(new URL(`../../${font.file}`, import.meta.url));
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(font.sha256);
    expect(bytes.subarray(0, 4).toString("latin1")).toBe("wOF2");
    expect(font.license).toContain("SIL Open Font License");
    expect(readFileSync(new URL(`../../${font.license_file}`, import.meta.url), "utf8")).toContain(
      "SIL OPEN FONT LICENSE",
    );
  }
  // The browser loads the local files; nothing is fetched from a font host at runtime.
  expect(css).toContain('url("/fonts/dm-sans-variable.woff2")');
  expect(css).toContain('url("/fonts/outfit-variable.woff2")');
  expect(css).toContain('format("woff2")');
});

test("the theme is plain v3-compatible CSS and is part of the bundle", () => {
  // Comments may name the v4 syntax; the declarations must not use it.
  expect(css.replace(/\/\*[\s\S]*?\*\//g, "")).not.toContain("@theme");
  expect(indexCss).toContain('@import "./styles/theme.css"');
  expect(indexCss).toContain("@tailwind base");
});
