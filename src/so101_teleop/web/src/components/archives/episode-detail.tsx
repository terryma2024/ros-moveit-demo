import { useMemo, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogClose } from '@/components/ui/dialog';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ArchiveNotice } from './archive-feedback';
import type { ArchivesApiClient, EpisodeDetailDto } from '@/api/archives-client';
import { Button } from '@/components/ui/button';
import { DataTable } from '@/components/ui/data-table';
import { useArchiveRequest } from './use-archive-request';
import { FramePlayer } from './frame-player';
import { SignalChart } from './signal-chart';
import { FileViewer } from './file-viewer';
import { ByteSize } from './byte-size';
import { MetadataTable } from './metadata-table';
function Summary({title,values,fields=Object.keys(values)}:{title:string;values:Record<string,unknown>;fields?:string[]}) {
  const [open,setOpen]=useState(false);
  const visible=fields.filter(key=>Object.hasOwn(values,key));
  return <Card role="region" aria-label={title} className="flex min-w-0 flex-col p-4">
    <h3 className="mb-2 font-semibold">{title}</h3>
    <dl className="flex-1 space-y-2 text-sm">{visible.map(key=><div key={key}>
      <dt className="text-muted-foreground">{key}</dt>
      <dd className="line-clamp-2 break-all whitespace-pre-wrap">{typeof values[key]==='object'?JSON.stringify(values[key]):String(values[key])}</dd>
    </div>)}</dl>
    {!visible.length&&<p className="text-sm text-muted-foreground">Summary unavailable.</p>}
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="outline" size="sm" className="mt-3 h-auto self-start whitespace-normal py-1">View full {title}</Button></DialogTrigger>
      {open&&<DialogContent>
        <DialogHeader><DialogTitle>{title}: full metadata</DialogTitle><DialogDescription>Complete metadata from this archive.</DialogDescription></DialogHeader>
        <div tabIndex={0} role="region" aria-label="Metadata table" className="min-h-0 overflow-auto rounded border"><MetadataTable values={values}/></div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Close</Button></DialogClose></DialogFooter>
      </DialogContent>}
    </Dialog>
  </Card>;
}
function ManifestFiles({api,packageId,sceneId,files,onView}:{api:ArchivesApiClient;packageId:string;sceneId:string;files:EpisodeDetailDto['files'];onView:(file:EpisodeDetailDto['files'][number])=>void}) {
  const columns=useMemo<ColumnDef<EpisodeDetailDto['files'][number]>[]>(()=>[
    {
      accessorKey:'name',header:'File',size:600,
      cell:({row:{original:entry}})=>(/\.jsonl?$/.test(entry.name)||entry.name.endsWith('.png'))
        ?<Button variant="link" className="h-auto max-w-full whitespace-normal text-left break-all" onClick={()=>onView(entry)}>{entry.name}</Button>
        :entry.name,
    },
    {accessorKey:'bytes',header:'Bytes',size:120,cell:({row})=><ByteSize value={row.original.bytes}/>},
    {accessorKey:'sha256',header:'SHA256',size:280,cell:({row})=><span className="text-xs">{row.original.sha256}</span>},
  ],[api,packageId,sceneId,onView]);
  return <section aria-label="Manifest files" className="space-y-3">
    <h3 className="font-semibold">Manifest files</h3>
    <DataTable columns={columns} data={files} getRowId={entry=>entry.file_id} label="Manifest files"/>
  </section>;
}
export function EpisodeDetail({api,packageId,sceneId,onBack}:{api:ArchivesApiClient;packageId:string;sceneId:string;onBack:()=>void}) {
  const request=useArchiveRequest(signal=>Promise.all([api.detail(packageId,sceneId,signal),api.series(packageId,sceneId,signal)]),[api,packageId,sceneId]);
  const [row,setRow]=useState(0);
  const [file,setFile]=useState<EpisodeDetailDto['files'][number]|null>(null);
  if(request.error) return <div><Button variant="outline" onClick={onBack}>Back to package</Button><ArchiveNotice error>{request.error.message}</ArchiveNotice></div>;
  if(!request.data) return <p role="status">Loading episode…</p>;
  const [detail,series]=request.data;
  return <section className="space-y-4"><Button variant="outline" onClick={onBack}>Back to package</Button><h2 className="text-xl font-semibold">Episode {detail.scene_id}</h2><p>Collection committed: <Badge variant="outline">{String(detail.collection_committed)}</Badge></p><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Summary title="Scene" values={detail.scene}/><Summary title="Episode seal" values={detail.seal} fields={['status','record_count','qc_passed','pick_place_validation_success','stopped_confirmed','committed']}/><Summary title="Processed result" values={detail.processed_result} fields={['act_data_status','act_data_qc','export_eligible','proc_attempt','act_data_reason','diagnostic_fault']}/><Summary title="QC summary" values={detail.qc_summary} fields={['status','reason','counts']}/></div>{detail.warnings.map((warning,i)=><ArchiveNotice key={i}>{warning}</ArchiveNotice>)}<section><h3 className="mb-2 font-semibold">Recording and processing attempts</h3><ol className="space-y-2 border-l-2 pl-4">{detail.attempts.map((attempt,i)=><li key={i}><Card className="p-3 text-sm"><strong className="capitalize">{attempt.kind}</strong> · round {attempt.round??'—'} · wave {attempt.wave??'—'} · shard {attempt.shard??'—'} · processor attempt {attempt.proc_attempt??'—'} · {attempt.outcome??'—'}<p className="whitespace-pre-wrap">{attempt.reason}</p></Card></li>)}</ol></section><FramePlayer api={api} packageId={packageId} sceneId={sceneId} frameCount={detail.frame_count} row={row} onRowChange={setRow} rowTimes={series.row_times_s}/><div className="grid gap-3 lg:grid-cols-2">{(['action','state'] as const).map(group=><SignalChart key={group} group={group} points={series.points} currentRow={row} currentTime={series.row_times_s[row]}/>)}</div><ManifestFiles key={`${packageId}-${sceneId}`} api={api} packageId={packageId} sceneId={sceneId} files={detail.files} onView={setFile}/>{file&&<FileViewer key={file.file_id} api={api} packageId={packageId} sceneId={sceneId} file={file} onClose={()=>setFile(null)}/>}</section>;
}
