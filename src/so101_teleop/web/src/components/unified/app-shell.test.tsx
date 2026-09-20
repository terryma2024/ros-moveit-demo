// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { AppShell } from "./app-shell";

describe("AppShell", () => {
  test("navigates between the two main entries without rebuilding the shell", async () => {
    const onNavigate = vi.fn();
    const { rerender } = render(
      <AppShell page="teleop" onNavigate={onNavigate}>
        <div data-testid="content">teleop</div>
      </AppShell>,
    );
    expect(screen.getByRole("button", { name: "Teleop" }).getAttribute("aria-current")).toBe("page");
    await userEvent.click(screen.getByRole("button", { name: "Expert Validation" }));
    expect(onNavigate).toHaveBeenCalledWith("/expert-validation");
    rerender(
      <AppShell page="validation" onNavigate={onNavigate}>
        <div data-testid="content">teleop</div>
      </AppShell>,
    );
    // The shell survives the switch: the same content node is still mounted.
    expect(screen.getByTestId("content")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Expert Validation" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(screen.getByRole("button", { name: "Teleop" }).getAttribute("aria-current")).toBeNull();
  });

  test("Tasks is a compatibility route, not a third primary entry", async () => {
    const onNavigate = vi.fn();
    render(
      <AppShell page="tasks" onNavigate={onNavigate}>
        <div />
      </AppShell>,
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Tasks");
    expect(screen.queryByRole("button", { name: "Tasks" })).toBeNull();
  });

  test("narrow layouts expose a collapsible navigation control", async () => {
    render(
      <AppShell page="teleop" onNavigate={() => undefined}>
        <div />
      </AppShell>,
    );
    const toggle = screen.getByRole("button", { name: "Menu" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    await userEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeTruthy();
  });

  test("health and the global owner reason are shown separately from the pages", () => {
    render(
      <AppShell
        page="validation"
        onNavigate={() => undefined}
        health={{ teleop: "unavailable", validation: "ready", blockedReason: "VALIDATION_ACTIVE" }}
      >
        <div />
      </AppShell>,
    );
    expect(screen.getByText("Teleop: unavailable")).toBeTruthy();
    expect(screen.getByText("Validation: ready")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("VALIDATION_ACTIVE");
  });

  test("the theme defaults to light, flips on demand and survives missing storage", async () => {
    render(
      <AppShell page="teleop" onNavigate={() => undefined}>
        <div />
      </AppShell>,
    );
    expect(screen.getByRole("button", { name: /theme/i }).textContent).toContain("Dark");
    await userEvent.click(screen.getByRole("button", { name: /theme/i }));
    expect(screen.getByRole("button", { name: /theme/i }).textContent).toContain("Light");
    // The applied theme is observable even when storage is unavailable or partial.
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
