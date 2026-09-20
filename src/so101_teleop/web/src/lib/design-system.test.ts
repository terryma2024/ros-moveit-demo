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

test("the lock never claims a component set or font it has not captured", () => {
  const lock = JSON.parse(readFileSync(new URL("../../design-system.lock.json", import.meta.url), "utf8"));
  expect(lock.blocked_reason).toContain("PENDING_REGISTRY_ITEMS");
  expect(lock.fonts).toEqual([]);
  expect(lock.registry.every((entry: { type?: string }) => entry.type === "registry:base")).toBe(true);
  // No guessed or "latest" versions: every recorded version is exact.
  expect(lock.tailwind.selected).toBe(lock.tailwind.from);
  expect(lock.cli.version).not.toBe("latest");
});
