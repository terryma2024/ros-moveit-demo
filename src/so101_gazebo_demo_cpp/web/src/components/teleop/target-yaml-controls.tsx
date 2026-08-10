import { useRef } from "react";
import type { ReplayableTarget } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { parseTargetYaml, serializeTargetYaml } from "@/lib/target-yaml";

export function TargetYamlControls({ target, onImport, onError }: { target: ReplayableTarget; onImport: (target: ReplayableTarget) => void; onError: (message: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const download = () => {
    const url = URL.createObjectURL(new Blob([serializeTargetYaml(target)], { type: "application/yaml" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "so101-target.yaml"; anchor.click(); URL.revokeObjectURL(url);
  };
  const upload = async (file?: File) => {
    if (!file) return;
    try { onImport(parseTargetYaml(await file.text())); } catch (error) { onError(String(error)); }
  };
  return <Card><CardTitle>Browser-only Target YAML</CardTitle><p className="my-3 text-sm text-slate-400">Contains Target joints, TCP and step frame only. Actual telemetry is never persisted.</p><div className="flex gap-2"><Button variant="secondary" onClick={download}>Download Target YAML</Button><Button variant="secondary" onClick={() => input.current?.click()}>Load Target YAML</Button><input ref={input} className="hidden" aria-label="Target YAML file" type="file" accept=".yaml,.yml,application/yaml,text/yaml" onChange={(event) => upload(event.target.files?.[0])}/></div></Card>;
}
