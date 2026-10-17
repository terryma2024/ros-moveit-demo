import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import type { ArchivesApiClient, EpisodeDetailDto } from '@/api/archives-client';
import { Button } from '@/components/ui/button';
import { useArchiveRequest } from './use-archive-request';
import { ByteSize } from './byte-size';
export function FileViewer({api,packageId,sceneId,file,onClose}:{api:ArchivesApiClient;packageId:string;sceneId:string;file:EpisodeDetailDto['files'][number];onClose:()=>void}) {
  const [offset,setOffset]=useState(0);
  const page=useArchiveRequest(signal=>api.file(packageId,sceneId,file.file_id,offset,100,signal),[api,packageId,sceneId,file.file_id,offset]);
  return <Dialog.Root open onOpenChange={open=>{if(!open)onClose();}}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-black/50"/><Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[min(95vw,60rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 rounded-lg border bg-background p-5 shadow-xl"><Dialog.Title className="break-all font-semibold">{file.name}</Dialog.Title><Dialog.Description className="text-sm text-muted-foreground"><ByteSize value={file.bytes}/> · SHA256 {file.sha256}</Dialog.Description>{page.loading&&<p role="status">Loading file…</p>}{page.error&&<p role="alert">{page.error.message}</p>}{page.data&&<pre className="overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-3 text-xs">{page.data.kind==='json'?JSON.stringify(page.data.content,null,2):(page.data.lines??[]).join('\n')}</pre>}<div className="flex gap-3"><Button variant="outline" disabled={offset===0||page.loading} onClick={()=>setOffset(0)}>First page</Button><Button disabled={page.loading||!page.data||page.data.eof||page.data.next_offset==null} onClick={()=>{if(page.data?.next_offset!=null)setOffset(page.data.next_offset);}}>Next page</Button><Dialog.Close asChild><Button variant="outline">Close</Button></Dialog.Close></div></Dialog.Content></Dialog.Portal></Dialog.Root>;
}
