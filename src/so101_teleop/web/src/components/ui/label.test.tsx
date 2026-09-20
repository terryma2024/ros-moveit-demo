// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { Label } from "./label";

describe("Label token port", () => {
  test("keeps the registry data slot and the token typography", () => {
    render(<Label htmlFor="field">Target</Label>);
    const label = screen.getByText("Target");
    expect(label.getAttribute("data-slot")).toBe("label");
    expect(label.getAttribute("for")).toBe("field");
    expect(label.className).toContain("text-sm");
    expect(label.className).toContain("font-medium");
  });

  test("clicking the label focuses its control", async () => {
    render(
      <>
        <Label htmlFor="field">Target</Label>
        <input id="field" aria-label="Target field" />
      </>,
    );
    await userEvent.click(screen.getByText("Target"));
    expect(document.activeElement?.id).toBe("field");
  });

  test("disabled state stays declared for assistive technology", () => {
    render(<Label className="group" data-disabled="true">Target</Label>);
    expect(screen.getByText("Target").className).toContain("group-data-[disabled=true]:opacity-50");
  });
});
