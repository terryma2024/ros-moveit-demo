import { Card, CardTitle } from "@/components/ui/card";

export type EventEntry = { at: string; operation: string; code: string; message?: string };

export function EventLog({ entries }: { entries: EventEntry[] }) {
  return <Card><CardTitle>Event log</CardTitle><div className="mt-3 max-h-64 overflow-auto"><table><thead><tr><th>Time</th><th>Operation</th><th>Code</th><th>Message</th></tr></thead><tbody>{entries.map((entry, index) => <tr key={`${entry.at}-${index}`}><td>{entry.at}</td><td>{entry.operation}</td><td>{entry.code}</td><td>{entry.message}</td></tr>)}</tbody></table></div></Card>;
}
