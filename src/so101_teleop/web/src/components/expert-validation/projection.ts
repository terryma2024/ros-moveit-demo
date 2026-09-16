export type Projection = {
  width_px: number;
  height_px: number;
  bounds_m: readonly number[];
  padding_px: number;
  pixels_per_m: number;
  offset_x_px: number;
  offset_y_px: number;
};

export type ProjectedBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export function projectXY(projection: Projection, x: number, y: number): [number, number] {
  return [
    Number((projection.offset_x_px + x * projection.pixels_per_m).toFixed(8)),
    Number((projection.offset_y_px - y * projection.pixels_per_m).toFixed(8)),
  ];
}

export function projectBounds(
  projection: Projection,
  bounds: readonly number[],
): ProjectedBounds {
  if (bounds.length !== 4) throw new Error("PROJECTION_BOUNDS");
  const [minimumX, maximumX, minimumY, maximumY] = bounds;
  const [left, bottom] = projectXY(projection, minimumX, minimumY);
  const [right, top] = projectXY(projection, maximumX, maximumY);
  return { x: left, y: top, width: right - left, height: bottom - top };
}
