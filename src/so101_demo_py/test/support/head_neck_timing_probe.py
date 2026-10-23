"""Head timing probe helpers: clock-diagnostic health and update continuity (the collector-based main is removed)."""
import json
from pathlib import Path
import time


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def clock_trace_health(directory, now_ns):
    """Check task-owned diagnostic streams without changing timing qualification."""
    try:
        for stream in ('physics', 'loop'):
            path = Path(directory) / f'{stream}.status.json'
            if path.is_symlink() or path.stat().st_size > 4096:
                raise ValueError('status path/size')
            row = json.loads(path.read_text())
            observed_ns = now_ns() if callable(now_ns) else now_ns
            age = observed_ns - row['heartbeat_ns']
            if (row['schema'] != 'SOCLK001' or row['stream'] != stream
                    or row['invalid_flags'] != 0 or row['final'] is not False
                    or not 0 <= age < 2_000_000_000):
                raise ValueError('invalid/stale status')
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError('CLOCK_DIAGNOSTIC_STATUS_INVALID') from error


def monitor_clock_traces(directory, cancelled, get_runtime, finished, errors, started_ns):
    """Supervise startup and holding; use the original Stop when it exists."""
    first_trace_ns = None
    both_seen = False
    while not finished.wait(.25):
        now = time.monotonic_ns()
        try:
            if now - started_ns >= 240_000_000_000 or cancelled.is_set():
                raise RuntimeError('CLOCK_DIAGNOSTIC_NORMAL_WORK_CANCELLED')
            present = [Path(directory, f'{stream}.status.json').is_file()
                       for stream in ('physics', 'loop')]
            begun = any(present) or any(Path(directory, f'{stream}.bin').is_file()
                                       for stream in ('physics', 'loop'))
            if begun and first_trace_ns is None:
                first_trace_ns = now
            if all(present):
                both_seen = True
                clock_trace_health(directory, time.monotonic_ns)
            elif both_seen or (first_trace_ns is not None and now - first_trace_ns >= 2_000_000_000):
                raise RuntimeError('CLOCK_DIAGNOSTIC_STATUS_MISSING')
        except Exception as error:
            errors.append(dict(type=type(error).__name__, message=str(error)))
            cancelled.set()
            current = get_runtime()
            if current is not None:
                try:
                    current.stop('unknown')
                except Exception as stop_error:
                    errors.append(dict(type=type(stop_error).__name__, message=str(stop_error)))
            return


def continuous_updates(updates, hold_start, hold_end):
    if any(after[3] != before[3] + 1 for before, after in zip(updates, updates[1:])):
        return False
    holding = [row for row in updates if hold_start <= row[8] <= hold_end]
    return all(after[6] == before[6] + 2_000_000
               for before, after in zip(holding, holding[1:]))


def main():
    """The in-controller timing collector is deleted with the broker (design 2026-10-10, section 6).

    The 120 s hold is measured from the ``controller_state`` topic and the controller manager's introspection
    topics by the Head nominal harness. The helpers above (clock diagnostic health, update continuity) stay
    because the diagnostic streams and their tests are independent of the controller.
    """
    raise RuntimeError('HEAD_TIMING_COLLECTOR_REMOVED')


if __name__ == '__main__':
    raise SystemExit(main())
