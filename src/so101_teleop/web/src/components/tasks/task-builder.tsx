import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import type { TaskPoint, TaskPointStatus } from "@/api/task-types";
import { Button } from "@/components/ui/button";

type Props = {
  presets: TaskPoint[];
  points: TaskPoint[];
  onChange: (points: TaskPoint[]) => void;
  reachability?: Record<string, TaskPointStatus>;
};

function replace(points: TaskPoint[], index: number, point: TaskPoint): TaskPoint[] {
  return points.map((current, currentIndex) => currentIndex === index ? point : current);
}

export function TaskBuilder({ presets, points, onChange, reachability = {} }: Props) {
  const [error, setError] = useState("");
  const duplicate = useMemo(() => {
    const ids = points.map((point) => point.id);
    return ids.find((id, index) => ids.indexOf(id) !== index);
  }, [points]);
  const shownError = duplicate ? "TASK_POINT_DUPLICATE_ID" : error;

  const addPreset = (preset: TaskPoint) => {
    if (points.some((point) => point.id === preset.id)) {
      setError("TASK_POINT_DUPLICATE_ID");
      return;
    }
    setError("");
    onChange([...points, {
      ...preset,
      cup_position_world_m: [...preset.cup_position_world_m] as [number, number, number],
    }]);
  };

  const addFree = () => {
    let index = 1;
    while (points.some((point) => point.id === `free_point_${index}`)) index += 1;
    setError("");
    onChange([...points, {
      id: `free_point_${index}`,
      label: `Free point ${index}`,
      cup_position_world_m: [0, -0.28, 0.165],
    }]);
  };

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= points.length) return;
    const next = [...points];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return <section className="space-y-4" aria-label="Task point builder">
    <div className="flex flex-wrap gap-2">
      {presets.map((preset) => <Button key={preset.id} type="button" variant="outline" onClick={() => addPreset(preset)} aria-label={`Add ${preset.id}`}>
        <Plus className="mr-1 h-4 w-4" />{preset.label}
      </Button>)}
      <Button type="button" onClick={addFree} aria-label="Add free point"><Plus className="mr-1 h-4 w-4" />Free point</Button>
    </div>
    {shownError && <p role="alert" className="text-sm text-red-400">{shownError}</p>}
    <div className="space-y-3">
      {points.map((point, index) => {
        const freeLabel = point.id.startsWith("free_point_") ? "Free point" : point.label;
        return <article key={index} className="grid gap-3 rounded-lg border border-slate-700 bg-slate-950/60 p-3 lg:grid-cols-[1fr_1fr_repeat(3,minmax(7rem,0.7fr))_auto]">
          <label className="grid gap-1 text-xs text-slate-400">Point ID
            <input value={point.id} onChange={(event) => onChange(replace(points, index, { ...point, id: event.target.value }))} />
          </label>
          <label className="grid gap-1 text-xs text-slate-400">Label
            <input value={point.label} onChange={(event) => onChange(replace(points, index, { ...point, label: event.target.value }))} />
          </label>
          {([0, 1, 2] as const).map((axis) => <label key={axis} className="grid gap-1 text-xs text-slate-400">
            {`${freeLabel} ${["X", "Y", "Z"][axis]} metres`}
            <input type="number" step="0.001" value={point.cup_position_world_m[axis]} onChange={(event) => {
              const xyz: [number, number, number] = [...point.cup_position_world_m];
              xyz[axis] = Number(event.target.value);
              onChange(replace(points, index, { ...point, cup_position_world_m: xyz }));
            }} />
          </label>)}
          <div className="flex items-end gap-1">
            <span className="mr-2 self-center rounded bg-slate-800 px-2 py-1 text-xs">{reachability[point.id] ?? "PENDING"}</span>
            <Button type="button" size="sm" variant="outline" onClick={() => move(index, -1)} disabled={index === 0} aria-label={`Move ${point.id} up`}><ArrowUp className="h-4 w-4" /></Button>
            <Button type="button" size="sm" variant="outline" onClick={() => move(index, 1)} disabled={index === points.length - 1} aria-label={`Move ${point.id} down`}><ArrowDown className="h-4 w-4" /></Button>
            <Button type="button" size="sm" variant="destructive" onClick={() => onChange(points.filter((_item, itemIndex) => itemIndex !== index))} aria-label={`Delete ${point.id}`}><Trash2 className="h-4 w-4" /></Button>
          </div>
        </article>;
      })}
    </div>
  </section>;
}
