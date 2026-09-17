import { createRoot } from "react-dom/client";

import { App } from "./app";
import { TaskApp } from "./task-app";
import { ExpertValidationApp } from "./expert-validation-app";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import "./index.css";

const Root = location.pathname.startsWith("/expert-validation")
  ? ExpertValidationApp
  : location.pathname === "/tasks" ? TaskApp : App;

createRoot(document.getElementById("root")!).render(<TooltipProvider><Root /><Toaster richColors position="top-right" /></TooltipProvider>);
