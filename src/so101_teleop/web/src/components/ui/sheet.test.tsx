// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { Button } from "./button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "./sheet";

describe("Sheet token port", () => {
  test("renders the trigger and keeps the registry class conversion", () => {
    // Radix mounts sheet content through a portal, which jsdom does not lay out; the open
    // interaction belongs to the browser gate. The class conversion is asserted on the source
    // contract instead: no v4-only utility survives in this file.
    const source = readFileSync("src/components/ui/sheet.tsx", "utf8");
    for (const klass of source.match(/"[^"]*"/g) ?? []) {
      expect(klass).not.toMatch(/\bsize-\d/);
      expect(klass).not.toMatch(/\/\d{2}["\s]/);
      expect(klass).not.toContain("rounded-4xl");
    }
    render(
      <Sheet>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Open navigation">
            X
          </Button>
        </SheetTrigger>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Navigation</SheetTitle>
            <SheetDescription>Teleop and Expert Validation</SheetDescription>
          </SheetHeader>
        </SheetContent>
      </Sheet>,
    );
    expect(screen.getByRole("button", { name: "Open navigation" })).toBeTruthy();
    expect(typeof SheetContent).toBe("function");
    expect(typeof SheetDescription).toBe("function");
  });

  test("the merged button keeps every registry variant available", () => {
    for (const variant of ["default", "secondary", "destructive", "outline", "ghost", "link"] as const) {
      render(<Button variant={variant}>label</Button>);
    }
    for (const size of ["default", "sm", "lg", "icon", "icon-sm", "xs"] as const) {
      render(<Button size={size}>label</Button>);
    }
    expect(screen.getAllByText("label").length).toBe(12);
  });
});
