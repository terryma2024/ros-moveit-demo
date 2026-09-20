import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const config = readFileSync(new URL("../../tailwind.config.ts", import.meta.url), "utf8");
const indexCss = readFileSync(new URL("../index.css", import.meta.url), "utf8");

test("Tailwind maps the semantic tokens onto the design-system variables", () => {
  for (const name of [
    "background",
    "foreground",
    "card",
    "popover",
    "primary",
    "secondary",
    "muted",
    "accent",
    "destructive",
    "border",
    "input",
    "ring",
    "sidebar",
  ]) {
    expect(config).toContain(`token("${name}")`);
  }
  // Business outcome utilities read the dedicated state variables.
  expect(config).toContain('success: token("state-success")');
  expect(config).toContain('pending: token("state-pending")');
  expect(config).toContain('failure: token("state-failure")');
  // Radius and fonts come from the same custom properties.
  expect(config).toContain('token("radius")');
  expect(config).toContain('token("font-sans")');
  expect(config).toContain('token("font-heading")');
  // Still Tailwind v3: no v4 @theme declaration leaks into the config or the CSS entry.
  // Comments may name the v4 syntax; only declarations count.
  const withoutComments = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  expect(withoutComments(config)).not.toContain("@theme");
  expect(withoutComments(indexCss)).not.toContain("@theme");
});

test("the page surface no longer hardcodes a slate palette", () => {
  expect(indexCss).toContain("@apply m-0 bg-background text-foreground");
  expect(indexCss).not.toContain("bg-slate-950 text-slate-100");
});

test("business outcome colours are not aliases of the brand colour", () => {
  expect(config).not.toMatch(/success:\s*token\("primary"\)/);
  expect(config).toContain('success: token("state-success")');
});
