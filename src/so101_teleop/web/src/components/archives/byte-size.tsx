const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB'];

export function ByteSize({ value }: { value: number | null | undefined }) {
  if (value == null || !Number.isFinite(value) || value < 0) return <span>—</span>;
  let scaled = value;
  let unit = 0;
  while (scaled >= 1024 && unit < units.length - 1) {
    scaled /= 1024;
    unit++;
  }
  return <span className="break-normal" title={`${value} bytes`}>{unit ? scaled.toFixed(2) : String(scaled)} {units[unit]}</span>;
}
