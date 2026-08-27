// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { TaskPoint } from "@/api/task-types";
import { TaskBuilder } from "./task-builder";

const presets: TaskPoint[] = [
  { id: "task_start", label: "Task start", cup_position_world_m: [0.02, -0.28, 0.165] },
  { id: "cup_test_left_5cm", label: "Left 5 cm", cup_position_world_m: [-0.03, -0.28, 0.165] },
];

function Harness({ changed }: { changed: (points: TaskPoint[]) => void }) {
  const [points, setPoints] = useState<TaskPoint[]>([]);
  return <TaskBuilder presets={presets} points={points} onChange={(next) => { setPoints(next); changed(next); }} />;
}

describe("TaskBuilder", () => {
  it("adds presets and arbitrary free points with controlled XYZ", async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Harness changed={changed} />);

    await user.click(screen.getByRole("button", { name: "Add task_start" }));
    await user.click(screen.getByRole("button", { name: "Add free point" }));
    const x = screen.getByLabelText("Free point X metres");
    await user.clear(x);
    await user.type(x, "0.01");

    expect(changed).toHaveBeenCalled();
    expect(screen.getByDisplayValue("free_point_1")).toBeTruthy();
    expect(screen.getByDisplayValue("0.01")).toBeTruthy();
  });

  it("preserves order and rejects duplicate IDs", async () => {
    const changed = vi.fn();
    const user = userEvent.setup();
    render(<Harness changed={changed} />);
    await user.click(screen.getByRole("button", { name: "Add task_start" }));
    await user.click(screen.getByRole("button", { name: "Add cup_test_left_5cm" }));
    await user.click(screen.getByRole("button", { name: "Move cup_test_left_5cm up" }));
    expect(changed.mock.calls.at(-1)?.[0].map((point: TaskPoint) => point.id)).toEqual([
      "cup_test_left_5cm", "task_start",
    ]);
    const secondId = screen.getByDisplayValue("task_start");
    await user.clear(secondId);
    await user.type(secondId, "cup_test_left_5cm");
    expect(screen.getByRole("alert").textContent).toContain("TASK_POINT_DUPLICATE_ID");
  });
});
