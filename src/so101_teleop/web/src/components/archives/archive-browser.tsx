import { useState } from 'react';
import { ArchiveError, ArchivesApiClient } from '@/api/archives-client';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useArchiveRouting } from './archive-routing';
import { EpisodeDetail } from './episode-detail';
import { PackageView } from './package-view';
import { useArchiveRequest } from './use-archive-request';
const defaultApi = new ArchivesApiClient();
export function ArchiveBrowser({ api = defaultApi }: { api?: ArchivesApiClient }) {
  const config = useArchiveRequest(signal=>api.config(signal),[api]);
  const {selection,choose} = useArchiveRouting();
  const root = selection.root??config.data?.roots[0]?.root_id;
  const [revision,refresh] = useState(0);
  const packages = useArchiveRequest(signal=>root?api.packages(root,revision>0,signal):null,[api,root,revision]);
  if (config.error) return <p role="alert">{config.error instanceof ArchiveError && config.error.code==='ARCHIVES_DISABLED'?'Archives are not enabled. Configure a search root when starting the server.':config.error.message}</p>;
  if (!config.data) return <p role="status">Loading archives…</p>;
  return <div className="space-y-5 p-4 md:p-6"><p className="text-sm text-muted-foreground">Browse sealed evidence, camera frames and signals. Integrity checks run only when requested.</p><div className="flex flex-wrap gap-3 items-end"><label>Search root<select aria-label="Search root" className="block rounded border bg-background p-2" value={root??''} onChange={e=>choose({root:e.target.value})}>{config.data.roots.map(item=><option key={item.root_id} value={item.root_id}>{item.label}</option>)}</select></label><Button variant="outline" onClick={()=>refresh(v=>v+1)}>Refresh packages</Button>{selection.pkg&&<Button variant="outline" onClick={()=>choose({root})}>All packages</Button>}</div>
    {packages.error&&<p role="alert">{packages.error.message}</p>}{packages.data?.warnings?.map((warning,i)=><p key={i}>{warning}</p>)}
    {selection.pkg&&selection.scene?<EpisodeDetail key={`${selection.pkg}-${selection.scene}`} api={api} packageId={selection.pkg} sceneId={selection.scene} onBack={()=>choose({root,pkg:selection.pkg})}/>:selection.pkg?<PackageView key={selection.pkg} api={api} packageId={selection.pkg} onScene={scene=>choose({root,pkg:selection.pkg,scene})}/>:<div className="overflow-x-auto rounded-lg border"><Table><TableHeader><TableRow>{['Package','Kind','Sealed','Reason','Files','Bytes','Manifest SHA256','Registered'].map(label=><TableHead key={label}>{label}</TableHead>)}</TableRow></TableHeader><TableBody>{packages.data?.packages.map(item=><TableRow key={item.package_id}><TableCell><Button variant="link" aria-label={`Open ${item.name}`} onClick={()=>choose({root,pkg:item.package_id})}>{item.name}</Button></TableCell><TableCell>{item.kind}</TableCell><TableCell>{item.sealed_at??'—'}</TableCell><TableCell>{item.reason??'—'}</TableCell><TableCell>{item.files}</TableCell><TableCell>{item.bytes}</TableCell><TableCell className="max-w-48 whitespace-normal break-all">{item.manifest_sha256}</TableCell><TableCell>{item.registered?'Yes':'No'}</TableCell></TableRow>)}</TableBody></Table></div>}
  </div>;
}
