import { createRoot } from "react-dom/client";

import { App } from "./app";
import { TaskApp } from "./task-app";
import { ExpertValidationApp } from "./expert-validation-app";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { createHttpTransport } from "@/api/domain-transport";
import { DomainRuntime } from "@/state/domain-runtime";
import { RuntimeProvider, usePageRouting } from "@/state/runtime-provider";
import "./index.css";

// The two domain runtimes live for the whole app: the root provider owns them once, and a
// page switch only changes which page is rendered.
const teleopRuntime = new DomainRuntime("teleop", createHttpTransport("teleop"));
const validationRuntime = new DomainRuntime("validation", createHttpTransport("validation"));

function UnifiedRoot() {
  const { page } = usePageRouting();
  if (page === "validation") return <ExpertValidationApp />;
  if (page === "tasks") return <TaskApp />;
  return <App />;
}

createRoot(document.getElementById("root")!).render(
  <TooltipProvider>
    <RuntimeProvider teleop={teleopRuntime} validation={validationRuntime}>
      <UnifiedRoot />
    </RuntimeProvider>
    <Toaster richColors position="top-right" />
  </TooltipProvider>,
);
