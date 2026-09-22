import { lstatSync } from "node:fs";
import { resolve, sep } from "node:path";

/**
 * The durable-evidence-root rule, platform bound.
 *
 * ai-station (Linux) keeps exactly one registered durable tree, `/data/work/so101-evidence/`; the
 * AGENTS.md evidence rule and every live gate there depend on it. macOS cannot satisfy it at all:
 * its root is a sealed, read-only system volume with no `/data` entry, and creating one needs root
 * authority this task does not have. The portability rule for that platform is narrow and still
 * fails closed - the registered root there is the task's own evidence root (`SO101_TASK_ROOT`,
 * the root the task opened in its ledger) and the run must live in a private directory inside it.
 *
 * This module is deliberately free of any test-runner import: the rule is a pure function of the
 * environment, the platform and the filesystem, so it can be exercised offline on either platform
 * without an operator authorization document and without spawning anything.
 */

/** The one registered durable tree on ai-station. */
export const DURABLE_EVIDENCE_PREFIX = "/data/work/so101-evidence/";

/** The environment variable naming the task's registered evidence root on macOS. */
export const REGISTERED_ROOT_ENV = "SO101_TASK_ROOT";

export type DurableRootFailure = "REQUIRED" | "NOT_PRIVATE";

export type DurableRootDeps = {
  platform?: NodeJS.Platform;
  uid?: number;
  /** Injectable for the platform branch that cannot exist on this host (ai-station's /data tree). */
  pathExists?: (path: string) => boolean;
  /** Injectable filesystem view; defaults to a real `lstat`. */
  pathInfo?: (path: string) => {
    isDirectory: boolean;
    isSymbolicLink: boolean;
    mode: number;
    uid: number;
  } | null;
};

function defaultPathInfo(path: string) {
  try {
    const info = lstatSync(path);
    return {
      isDirectory: info.isDirectory(),
      isSymbolicLink: info.isSymbolicLink(),
      mode: info.mode & 0o777,
      uid: info.uid,
    };
  } catch {
    return null;
  }
}

/**
 * Why `value` is not a durable evidence root, or `null` when it is one.
 *
 * `REQUIRED` covers everything that means "this is not a registered root": an empty value, a
 * relative path, a path outside the registered tree, or a path that does not exist. `NOT_PRIVATE`
 * is narrower and only ever applies inside the registered tree: a symlink, a non-directory, a path
 * owned by another account, or a directory group/other can read.
 */
export function durableRootFailure(
  value: string,
  environment: NodeJS.ProcessEnv,
  deps: DurableRootDeps = {},
): DurableRootFailure | null {
  const platform = deps.platform ?? process.platform;
  const pathExists = deps.pathExists ?? ((path: string) => defaultPathInfo(path) !== null);
  const pathInfo = deps.pathInfo ?? defaultPathInfo;
  const uid = deps.uid ?? (typeof process.getuid === "function" ? process.getuid() : -1);

  if (platform !== "darwin") {
    if (!value.startsWith(DURABLE_EVIDENCE_PREFIX) || !pathExists(value)) return "REQUIRED";
    return null;
  }

  const registered = environment[REGISTERED_ROOT_ENV] ?? "";
  if (!registered.startsWith("/") || !value.startsWith("/")) return "REQUIRED";
  const registeredRoot = resolve(registered);
  const root = resolve(value);
  if (root !== registeredRoot && !root.startsWith(registeredRoot + sep)) return "REQUIRED";

  for (const candidate of [registeredRoot, root]) {
    const info = pathInfo(candidate);
    if (info === null) return "REQUIRED";
    if (info.isSymbolicLink || !info.isDirectory) return "NOT_PRIVATE";
    if (uid >= 0 && info.uid !== uid) return "NOT_PRIVATE";
  }
  const run = pathInfo(root);
  if (run === null) return "REQUIRED";
  if ((run.mode & 0o077) !== 0) return "NOT_PRIVATE";
  return null;
}
