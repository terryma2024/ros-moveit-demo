import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const css = readFileSync(new URL("./unified-layout.css", import.meta.url), "utf8");
const indexCss = readFileSync(new URL("../index.css", import.meta.url), "utf8");

function rule(selector: string, body: string): RegExp {
  return new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[^{]*\\{[^}]*${body}`, "s");
}

test("the validation page keeps the approved 60/40 split with a full-width map", () => {
  // Proportion, not pixels: minmax(0, ...) lets the map fill its column without overflowing.
  expect(rule(".validation-layout", "minmax\\(0, 3fr\\) minmax\\(0, 2fr\\)").test(css)).toBe(true);
  expect(rule(".validation-map", "width:\\s*100%").test(css)).toBe(true);
  // The map must not be clipped or letterboxed by a small max-width.
  expect(rule(".validation-map svg", "max-width:\\s*none").test(css)).toBe(true);
  expect(rule(".validation-map svg", "height:\\s*auto").test(css)).toBe(true);
});

test("point results step down 3 to 2 to 1 columns and the split collapses on narrow screens", () => {
  expect(rule(".point-results", "repeat\\(3, minmax\\(0, 1fr\\)\\)").test(css)).toBe(true);
  expect(css).toMatch(/@media \(max-width: 1100px\)[\s\S]*?\.point-results[\s\S]*?repeat\(2, minmax\(0, 1fr\)\)/);
  expect(css).toMatch(/@media \(max-width: 360px\)[\s\S]*?\.point-results[\s\S]*?minmax\(0, 1fr\)/);
  expect(css).toMatch(/@media \(max-width: 760px\)[\s\S]*?\.validation-layout[\s\S]*?minmax\(0, 1fr\)/);
});

test("the dense joint table scrolls inside itself instead of overflowing the page", () => {
  expect(rule(".teleop-joint-table", "overflow-x:\\s*auto").test(css)).toBe(true);
  expect(rule(".unified-main", "min-width:\\s*0").test(css)).toBe(true);
});

test("the shell collapses its navigation only below the wide breakpoint", () => {
  expect(css).toMatch(/@media \(min-width: 901px\)[\s\S]*?display:\s*block/);
  expect(css).toMatch(/@media \(max-width: 900px\)[\s\S]*?\.unified-nav\[data-collapsed="true"\][\s\S]*?display:\s*none/);
});

test("the layout stylesheet is part of the built bundle", () => {
  expect(indexCss).toContain('@import "./styles/unified-layout.css"');
});
