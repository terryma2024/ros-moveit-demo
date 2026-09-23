// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { Input } from "./input";

describe("Input token port", () => {
  test("keeps the registry data slot and accepts ordinary input props", async () => {
    const onChange = vi.fn();
    render(<Input aria-label="Target" defaultValue="" onChange={onChange} />);
    const field = screen.getByLabelText("Target");
    expect(field.getAttribute("data-slot")).toBe("input");
    await userEvent.type(field, "abc");
    expect(onChange).toHaveBeenCalled();
  });

  test("uses tokens and no v4-only classes", () => {
    render(<Input aria-label="Target" />);
    const className = screen.getByLabelText("Target").className;
    for (const token of ["border-input", "bg-card", "text-foreground", "text-muted-foreground", "ring-ring", "rounded-md"]) {
      expect(className).toContain(token);
    }
    for (const v4Only of ["rounded-4xl", "/30", "/50", "outline-none ring"]) {
      expect(className).not.toContain(v4Only);
    }
  });

  test("disabled and invalid states stay declared for assistive technology", () => {
    render(<Input aria-label="Target" disabled aria-invalid />);
    const field = screen.getByLabelText("Target") as HTMLInputElement;
    expect(field.disabled).toBe(true);
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(field.className).toContain("disabled:opacity-70");
    expect(field.className).toContain("aria-invalid:border-destructive");
  });
});
