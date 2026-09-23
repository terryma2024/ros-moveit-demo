import { readFileSync, readdirSync } from "node:fs";
import { expect, test } from "vitest";

const UI = new URL(".", import.meta.url);

test("no primitive keeps a hardcoded palette colour", () => {
  const offenders: string[] = [];
  for (const name of readdirSync(UI).filter((entry) => entry.endsWith(".tsx"))) {
    const source = readFileSync(new URL(name, UI), "utf8");
    for (const match of source.matchAll(/\b(?:bg|text|border|ring|fill|stroke)-(?:slate|zinc|neutral|gray|stone)-[0-9]{2,3}\b/g)) {
      offenders.push(`${name}:${match[0]}`);
    }
  }
  expect(offenders).toEqual([]);
});

test("the button keeps every business variant while using tokens", () => {
  const button = readFileSync(new URL("button.tsx", UI), "utf8");
  for (const variant of ["default", "secondary", "destructive", "outline"]) {
    expect(button).toContain(`${variant}:`);
  }
  for (const size of ["default", "sm", "lg"]) expect(button).toContain(`${size}:`);
  expect(button).toContain("disabled:bg-muted disabled:text-muted-foreground");
  expect(button).toContain("focus-visible:ring-2");
  expect(button).toContain("bg-destructive text-white");
});

test("card and dialog surfaces read the semantic tokens", () => {
  const card = readFileSync(new URL("card.tsx", UI), "utf8");
  expect(card).toContain("border-border");
  expect(card).toContain("bg-card");
  expect(card).toContain("text-card-foreground");
  expect(card).toContain("text-muted-foreground");
  const dialog = readFileSync(new URL("alert-dialog.tsx", UI), "utf8");
  expect(dialog).toContain("border-border bg-card");
});
