import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("locks the requested full preset and retains independent Radix base", () => {
  const lock = JSON.parse(readFileSync(new URL("../../design-system.lock.json", import.meta.url), "utf8"));
  expect(lock.cli.version).toBe("4.21.0");
  expect(lock.preset).toBe("b311momZs0");
  expect(lock.base).toBe("radix");
  expect(lock.decoded).toMatchObject({
    style: "maia",
    baseColor: "mist",
    theme: "blue",
    chartColor: "mist",
    iconLibrary: "lucide",
    font: "dm-sans",
    fontHeading: "outfit",
    radius: "large",
    menuAccent: "subtle",
    menuColor: "default",
  });
  expect(lock.registry.length).toBeGreaterThan(0);
  for (const entry of lock.registry) expect(entry.sha256).toMatch(/^[a-f0-9]{64}$/);
});

test("the lock captures every radix-maia item it needs, with the font items included", () => {
  const lock = JSON.parse(readFileSync(new URL("../../design-system.lock.json", import.meta.url), "utf8"));
  const names = lock.registry.map((entry: { name: string }) => entry.name);
  expect(names).toContain("radix-maia");
  for (const item of [
    "utils",
    "font-dm-sans",
    "font-heading-outfit",
    "sidebar",
    "sheet",
    "field",
    "select",
    "input",
    "label",
    "badge",
    "card",
    "button",
    "alert-dialog",
    "tooltip",
    "separator",
    "tabs",
    "scroll-area",
  ]) {
    expect(names).toContain(item);
  }
  // Every entry is a real fetch of the radix-maia style with its own hash.
  for (const entry of lock.registry.slice(1)) {
    expect(entry.url).toContain("/r/styles/radix-maia/");
    expect(entry.sha256).toMatch(/^[a-f0-9]{64}$/);
  }
  expect(lock.blocked_reason).toContain("PENDING_PRODUCT_MERGE");
  expect(lock.fonts).toHaveLength(2);
  for (const font of lock.fonts) {
    expect(font.family).toBeTruthy();
    expect(font.sha256).toMatch(/^[a-f0-9]{64}$/);
  }
  // No guessed or "latest" versions: every recorded version is exact.
  expect(lock.tailwind.selected).toBe(lock.tailwind.from);
  expect(lock.cli.version).not.toBe("latest");
});
