import { execFileSync } from "node:child_process";

/** Identify test-only descendants by both the helper script and this run's exact root. */
function ownedDescendantPids(ownerRoot: string): number[] {
  const listing = execFileSync("ps", ["-Aww", "-o", "pid=", "-o", "command="], {
    encoding: "utf-8",
  });
  const marker = `process_helpers/descendant_helper.py --owner-root ${ownerRoot}`;
  return listing.split("\n").flatMap((line) => {
    const match = line.match(/^\s*(\d+)\s+(.*)$/);
    if (!match) return [];
    const position = match[2].indexOf(marker);
    if (position < 0) return [];
    const after = match[2].charAt(position + marker.length);
    return after === "" || /\s/.test(after) ? [Number(match[1])] : [];
  });
}

/** Reap fixture-owned descendants even when an assertion skipped the test's own finally block. */
export async function stopOwnedDescendants(ownerRoot: string): Promise<number[]> {
  const original = ownedDescendantPids(ownerRoot);
  for (const pid of original) {
    if (!ownedDescendantPids(ownerRoot).includes(pid)) continue;
    try {
      process.kill(pid, "SIGTERM");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
    }
  }
  const deadline = Date.now() + 2_000;
  while (ownedDescendantPids(ownerRoot).length > 0 && Date.now() < deadline) {
    await new Promise((done) => setTimeout(done, 50));
  }
  for (const pid of ownedDescendantPids(ownerRoot)) {
    if (!ownedDescendantPids(ownerRoot).includes(pid)) continue;
    try {
      process.kill(pid, "SIGKILL");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
    }
  }
  const survivors = ownedDescendantPids(ownerRoot);
  if (survivors.length > 0) {
    throw new Error(`OWNED_DESCENDANT_LEAK: ${survivors.join(",")}`);
  }
  return original;
}
