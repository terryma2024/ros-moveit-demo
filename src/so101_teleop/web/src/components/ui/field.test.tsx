// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "./field";

describe("Field token port", () => {
  test("renders the registry data slots with tokens", () => {
    const { container } = render(
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="n">Worker count</FieldLabel>
          <FieldDescription>Exact N per batch</FieldDescription>
          <FieldError>EXACT_N_UNQUALIFIED</FieldError>
        </Field>
      </FieldGroup>,
    );
    for (const slot of ["field-group", "field", "field-label", "field-description", "field-error"]) {
      expect(container.querySelector(`[data-slot="${slot}"]`)).toBeTruthy();
    }
    expect(screen.getByText("Exact N per batch").className).toContain("text-muted-foreground");
    expect(screen.getByText("EXACT_N_UNQUALIFIED").className).toContain("text-destructive");
  });

  test("no v4-only utility survives in the ported classes", () => {
    const { container } = render(
      <Field>
        <FieldDescription>hint</FieldDescription>
      </Field>,
    );
    for (const element of Array.from(container.querySelectorAll<HTMLElement>("[data-slot]"))) {
      for (const klass of element.className.split(/\s+/)) {
        expect(klass).not.toMatch(/^(?:size|rounded-4xl)-/);
        expect(klass).not.toMatch(/\/\d{2}$/);
      }
    }
  });
});
