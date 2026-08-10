import { createRoot } from "react-dom/client";

import { App } from "./app";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import "./index.css";

createRoot(document.getElementById("root")!).render(<TooltipProvider><App /><Toaster richColors position="top-right" /></TooltipProvider>);
