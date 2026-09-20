// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select";

function Harness() {
  return (
    <Select>
      <SelectTrigger aria-label="Worker count">
        <SelectValue placeholder="pick" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="2">2</SelectItem>
        <SelectItem value="4">4</SelectItem>
      </SelectContent>
    </Select>
  );
}

describe("Select token port", () => {
  test("renders a combobox trigger carrying the registry data slot", () => {
    render(<Harness />);
    const trigger = screen.getByRole("combobox", { name: "Worker count" });
    expect(trigger.getAttribute("data-slot")).toBe("select-trigger");
    expect(trigger.className).toContain("border-input");
    // No standalone v4 utility survives: `[&_svg:not([class*='size-'])]` is selector text and
    // may keep the word, but no class of this element is a v4 `size-*` or alpha modifier.
    for (const klass of trigger.className.split(/\s+/)) {
      expect(klass).not.toMatch(/^size-\d/);
      expect(klass).not.toMatch(/\/\d{2}$/);
    }
  });

  test("exports the full registry surface and renders closed", () => {
    // Radix renders its listbox into a portal and calls scrollIntoView, neither of which jsdom
    // provides; the open/select interaction belongs to the browser gate (Task 11), not here.
    expect(typeof SelectContent).toBe("function");
    expect(typeof SelectItem).toBe("function");
    render(<Harness />);
    expect(screen.getByRole("combobox", { name: "Worker count" })).toBeTruthy();
  });

});
