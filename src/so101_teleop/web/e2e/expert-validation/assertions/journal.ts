import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export type JournalEvent = {
  kind: string;
  type?: string;
  sequence?: number;
  idempotency_key?: string;
  payload: Record<string, unknown>;
};

function parseJournalFile(path: string): JournalEvent[] {
  const data = readFileSync(path);
  const events: JournalEvent[] = [];
  let offset = 0;
  while (offset < data.length) {
    const jsonLength = data.readUInt32BE(offset + 4);
    const sha = data.subarray(offset + 8, offset + 72).toString("utf-8");
    if (!/^[0-9a-f]{64}$/.test(sha)) {
      throw new Error(`JOURNAL_FRAME_INVALID: ${path} @${offset}`);
    }
    const document = JSON.parse(
      data.subarray(offset + 72, offset + 72 + jsonLength).toString("utf-8"),
    ) as JournalEvent;
    if (data[offset + 72 + jsonLength] !== 0x0a) {
      throw new Error(`JOURNAL_FRAME_TERMINATOR_MISSING: ${path} @${offset}`);
    }
    events.push(document);
    offset += 73 + jsonLength;
  }
  return events;
}

export function readJournalEvents(journalRoot: string): JournalEvent[] {
  const eventsDir = join(journalRoot, "events");
  if (!existsSync(eventsDir)) return [];
  const segments = readdirSync(eventsDir)
    .filter((name) => name.endsWith(".journal"))
    .sort();
  return segments.flatMap((name) => parseJournalFile(join(eventsDir, name)));
}

export function storeQuery(python: string, database: string, sql: string): unknown {
  const output = execFileSync(
    python,
    [
      "-c",
      "import json, sqlite3, sys\n"
        + "connection = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)\n"
        + "connection.row_factory = sqlite3.Row\n"
        + "print(json.dumps([dict(row) for row in connection.execute(sys.argv[2])]))\n",
      database,
      sql,
    ],
    { encoding: "utf-8" },
  );
  return JSON.parse(output);
}
