/**
 * The app-lifetime root provider.
 *
 * It owns exactly two domain runtimes and hands them to the pages. Switching pages must not
 * recreate a runtime, drop a subscription, release a lease or stop a renewal: only an explicit
 * `dispose` on unmount ends them.
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { DomainName } from "@/api/instance-client";
import type { DomainRuntime } from "./domain-runtime";

export type PageName = "teleop" | "validation" | "tasks";

export function pageFromPath(pathname: string): PageName {
  if (pathname.startsWith("/expert-validation")) return "validation";
  if (pathname === "/tasks" || pathname.startsWith("/tasks/")) return "tasks";
  return "teleop";
}

type RuntimeRegistry = {
  teleop: DomainRuntime | null;
  validation: DomainRuntime | null;
  notices: string[];
  register: (domain: DomainName, runtime: DomainRuntime) => void;
};

const RuntimeContext = createContext<RuntimeRegistry | null>(null);

export function RuntimeProvider({
  children,
  teleop = null,
  validation = null,
  heartbeatMs,
}: {
  children: ReactNode;
  teleop?: DomainRuntime | null;
  validation?: DomainRuntime | null;
  /**
   * Renewal cadence for both domains. The heartbeat belongs to the runtime, so a page switch never
   * stops it and only this provider unmounting does.
   */
  heartbeatMs?: number;
}) {
  const [notices, setNotices] = useState<string[]>([]);
  const [registered, setRegistered] = useState<{ teleop: DomainRuntime | null; validation: DomainRuntime | null }>({
    teleop,
    validation,
  });

  useEffect(() => {
    setRegistered({ teleop, validation });
    const started: DomainRuntime[] = [];
    for (const runtime of [teleop, validation]) {
      if (!runtime) continue;
      started.push(runtime);
      void runtime
        .start()
        .then(() => {
          if (heartbeatMs !== undefined) runtime.startHeartbeat(heartbeatMs);
        })
        .catch((error: unknown) => {
          setNotices((current) => [...current, `DOMAIN_UNAVAILABLE: ${String(error)}`]);
        });
    }
    return () => {
      // The provider owns the runtimes for the whole app, so disposal happens only when the
      // provider itself unmounts — never on a page switch.
      for (const runtime of started) runtime.dispose();
    };
  }, [teleop, validation, heartbeatMs]);

  const value = useMemo<RuntimeRegistry>(
    () => ({
      teleop: registered.teleop,
      validation: registered.validation,
      notices,
      register: (domain, runtime) =>
        setRegistered((current) => ({ ...current, [domain]: runtime })),
    }),
    [registered, notices],
  );

  return <RuntimeContext.Provider value={value}>{children}</RuntimeContext.Provider>;
}

export function useRuntimeRegistry(): RuntimeRegistry {
  const value = useContext(RuntimeContext);
  if (!value) throw new Error("RUNTIME_PROVIDER_MISSING");
  return value;
}

export function useDomainRuntime(domain: DomainName): DomainRuntime {
  const registry = useRuntimeRegistry();
  const runtime = domain === "validation" ? registry.validation : registry.teleop;
  if (!runtime) throw new Error(`DOMAIN_RUNTIME_MISSING: ${domain}`);
  return runtime;
}

/** History-API routing: navigation updates page state without remounting the provider. */
export function usePageRouting(
  initial: PageName = pageFromPath(globalThis.location?.pathname ?? "/"),
): { page: PageName; navigate: (path: string) => void } {
  const [page, setPage] = useState<PageName>(initial);
  useEffect(() => {
    const onPopState = () => setPage(pageFromPath(globalThis.location.pathname));
    globalThis.addEventListener("popstate", onPopState);
    return () => globalThis.removeEventListener("popstate", onPopState);
  }, []);
  const navigate = (path: string) => {
    if (globalThis.location && globalThis.history) {
      globalThis.history.pushState({}, "", path);
    }
    setPage(pageFromPath(path));
  };
  return { page, navigate };
}
