import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import type { ArchivesApiClient, EpisodeDetailDto } from '@/api/archives-client';
import { Button, buttonVariants } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useArchiveRequest } from './use-archive-request';
import { FramePlayer } from './frame-player';
import { SignalChart } from './signal-chart';
import { FileViewer } from './file-viewer';
import { ByteSize } from './byte-size';
import { MetadataTable } from './metadata-table';
function Summary({title,values,fields=Object.keys(values)}:{title:string;values:Record<string,unknown>;fields?:string[]}) {
  const [open,setOpen]=useState(false);
  const visible=fields.filter(key=>Object.hasOwn(values,key));
  return <section aria-label={title} className="flex min-w-0 flex-col rounded-lg border bg-card p-4">
    <h3 className="mb-2 font-semibold">{title}</h3>
    <dl className="flex-1 space-y-2 text-sm">{visible.map(key=><div key={key}>
      <dt className="text-muted-foreground">{key}</dt>
      <dd className="line-clamp-2 break-all whitespace-pre-wrap">{typeof values[key]==='object'?JSON.stringify(values[key]):String(values[key])}</dd>
    </div>)}</dl>
    {!visible.length&&<p className="text-sm text-muted-foreground">Summary unavailable.</p>}
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild><Button variant="outline" size="sm" className="mt-3 h-auto self-start whitespace-normal py-1">View full {title}</Button></Dialog.Trigger>
      {open&&<Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50"/>
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[min(95vw,60rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 rounded-lg border bg-background p-5 shadow-xl">
          <Dialog.Title className="shrink-0 font-semibold">{title}: full metadata</Dialog.Title>
          <Dialog.Description className="shrink-0 text-sm text-muted-foreground">Complete metadata from this archive.</Dialog.Description>
          <div tabIndex={0} role="region" aria-label="Metadata table" className="min-h-0 overflow-auto rounded border"><MetadataTable values={values}/></div>
          <Dialog.Close asChild><Button variant="outline" className="shrink-0 self-end">Close</Button></Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>}
    </Dialog.Root>
  </section>;
}
export function EpisodeDetail({api,packageId,sceneId,onBack}:{api:ArchivesApiClient;packageId:string;sceneId:string;onBack:()=>void}) {
  const request=useArchiveRequest(signal=>Promise.all([api.detail(packageId,sceneId,signal),api.series(packageId,sceneId,signal)]),[api,packageId,sceneId]);
  const [row,setRow]=useState(0);
  const [file,setFile]=useState<EpisodeDetailDto['files'][number]|null>(null);
  if(request.error) return <div><Button variant="outline" onClick={onBack}>Back to package</Button><p role="alert">{request.error.message}</p></div>;
  if(!request.data) return <p role="status">Loading episode…</p>;
  const [detail,series]=request.data;
  return <section className="space-y-4"><Button variant="outline" onClick={onBack}>Back to package</Button><h2 className="text-xl font-semibold">Episode {detail.scene_id}</h2><p>Collection committed: {String(detail.collection_committed)}</p><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Summary title="Scene" values={detail.scene}/><Summary title="Episode seal" values={detail.seal} fields={['status','record_count','qc_passed','pick_place_validation_success','stopped_confirmed','committed']}/><Summary title="Processed result" values={detail.processed_result} fields={['act_data_status','act_data_qc','export_eligible','proc_attempt','act_data_reason','diagnostic_fault']}/><Summary title="QC summary" values={detail.qc_summary} fields={['status','reason','counts']}/></div>{detail.warnings.map((warning,i)=><p key={i}>{warning}</p>)}<section><h3 className="mb-2 font-semibold">Recording and processing attempts</h3><ol className="space-y-2 border-l-2 pl-4">{detail.attempts.map((attempt,i)=><li key={i} className="rounded border p-3 text-sm"><strong className="capitalize">{attempt.kind}</strong> · round {attempt.round??'—'} · wave {attempt.wave??'—'} · shard {attempt.shard??'—'} · processor attempt {attempt.proc_attempt??'—'} · {attempt.outcome??'—'}<p className="whitespace-pre-wrap">{attempt.reason}</p></li>)}</ol></section><FramePlayer api={api} packageId={packageId} sceneId={sceneId} frameCount={detail.frame_count} row={row} onRowChange={setRow} rowTimes={series.row_times_s}/><div className="grid gap-3 lg:grid-cols-2">{(['action','state'] as const).map(group=><SignalChart key={group} group={group} points={series.points} currentRow={row} currentTime={series.row_times_s[row]}/>)}</div><h3 className="font-semibold">Manifest files</h3><div className="overflow-x-auto rounded border"><Table><TableHeader><TableRow><TableHead>File</TableHead><TableHead>Bytes</TableHead><TableHead>SHA256</TableHead></TableRow></TableHeader><TableBody>{detail.files.map(entry=><TableRow key={entry.file_id}><TableCell>{/\.jsonl?$/.test(entry.name)?<Button variant="link" className="h-auto whitespace-normal text-left break-all" onClick={()=>setFile(entry)}>{entry.name}</Button>:entry.name.endsWith('.png')?<a className={buttonVariants({variant:"link",className:"h-auto whitespace-normal text-left break-all"})} href={api.downloadUrl(packageId,sceneId,entry.file_id)} download={entry.name.split('/').at(-1)} title="Download PNG">{entry.name}</a>:entry.name}</TableCell><TableCell><ByteSize value={entry.bytes}/></TableCell><TableCell className="max-w-64 whitespace-normal break-all text-xs">{entry.sha256}</TableCell></TableRow>)}</TableBody></Table></div>{file&&<FileViewer key={file.file_id} api={api} packageId={packageId} sceneId={sceneId} file={file} onClose={()=>setFile(null)}/>}</section>;
}
