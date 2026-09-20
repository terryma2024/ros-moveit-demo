/**
 * The shared shell: theme, navigation, and the two domain entry points.
 *
 * It is *not* a shared business lease. The shell only selects which page is shown; leases,
 * sessions and command identifiers stay with each domain's own runtime. Tasks keeps its legacy
 * `/tasks` route as a compatibility link rather than becoming a third product area.
 */
import { useEffect, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import "@/styles/unified-layout.css";

export type ShellPage = "teleop" | "validation" | "tasks";

export type DomainHealth = {
  teleop: "ready" | "unavailable" | "blocked";
  validation: "ready" | "unavailable" | "blocked";
  blockedReason?: string | null;
};

const PAGES: { page: ShellPage; path: string; label: string }[] = [
  { page: "teleop", path: "/", label: "Teleop" },
  { page: "validation", path: "/expert-validation", label: "Expert Validation" },
];

const THEME_KEY = "so101-unified-theme";

export function AppShell({
  page,
  onNavigate,
  health,
  children,
}: {
  page: ShellPage;
  onNavigate: (path: string) => void;
  health?: DomainHealth;
  children: ReactNode;
}) {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    // Light is the default; the user's choice persists, and an unavailable storage must not
    // block control.
    try {
      const stored = globalThis.localStorage?.getItem(THEME_KEY);
      return stored === "dark" ? "dark" : "light";
    } catch {
      return "light";
    }
  });
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    try {
      globalThis.localStorage?.setItem(THEME_KEY, theme);
    } catch {
      /* storage is optional */
    }
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const navigate = (path: string) => {
    setNavOpen(false);
    onNavigate(path);
  };

  return (
    <div className="unified-shell" data-theme={theme}>
      <nav className="unified-sidebar" aria-label="Primary">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold">SO-101</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-expanded={navOpen}
            aria-controls="unified-navigation"
            onClick={() => setNavOpen((open) => !open)}
          >
            Menu
          </Button>
        </div>
        <Separator className="my-3" />
        <ul
          id="unified-navigation"
          className="unified-nav space-y-2"
          data-collapsed={navOpen ? "false" : "true"}
        >
          {PAGES.map((entry) => (
            <li key={entry.page}>
              <Button
                type="button"
                variant={page === entry.page ? "secondary" : "outline"}
                className="w-full justify-start"
                aria-current={page === entry.page ? "page" : undefined}
                onClick={() => navigate(entry.path)}
              >
                {entry.label}
              </Button>
            </li>
          ))}
        </ul>
      </nav>
      <main className="unified-main">
        <header className="unified-topbar">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold">
              {PAGES.find((entry) => entry.page === page)?.label ?? "Tasks (compatibility)"}
            </h1>
            {health ? (
              <>
                <Badge variant={health.teleop === "ready" ? "secondary" : "destructive"}>
                  Teleop: {health.teleop}
                </Badge>
                <Badge variant={health.validation === "ready" ? "secondary" : "destructive"}>
                  Validation: {health.validation}
                </Badge>
              </>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {health?.blockedReason ? (
              <span role="status" className="text-sm">
                Global owner: {health.blockedReason}
              </span>
            ) : null}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? "Light" : "Dark"} theme
            </Button>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
