import { useRef, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogClose } from '@/components/ui/dialog';
import type { ArchivesApiClient, EpisodeDetailDto } from '@/api/archives-client';
import { Button, buttonVariants } from '@/components/ui/button';
import { useArchiveRequest } from './use-archive-request';
import { ByteSize } from './byte-size';
import { ArchiveNotice } from './archive-feedback';
export function FileViewer({api,packageId,sceneId,file,onClose}:{api:ArchivesApiClient;packageId:string;sceneId:string;file:EpisodeDetailDto['files'][number];onClose:()=>void}) {
  const [offset,setOffset]=useState(0);
  const returnFocus=useRef(document.activeElement as HTMLElement|null);
  const image=file.name.endsWith('.png');
  const [imageFailed,setImageFailed]=useState(false);
  const page=useArchiveRequest(signal=>image?null:api.file(packageId,sceneId,file.file_id,offset,100,signal),[api,packageId,sceneId,file.file_id,offset,image]);
  return <Dialog open onOpenChange={open=>{if(!open)onClose();}}><DialogContent onCloseAutoFocus={event=>{event.preventDefault();if(returnFocus.current?.isConnected)returnFocus.current.focus({preventScroll:true});}}>
    <DialogHeader><DialogTitle>{file.name}</DialogTitle><DialogDescription><ByteSize value={file.bytes}/> · SHA256 {file.sha256}</DialogDescription></DialogHeader>
    {image?<div className="min-h-0 overflow-auto rounded bg-muted p-2">
      <img alt={file.name} src={api.downloadUrl(packageId,sceneId,file.file_id)} className="mx-auto max-h-[60vh] max-w-full object-contain" onError={()=>setImageFailed(true)}/>
      {imageFailed&&<ArchiveNotice error>Image preview unavailable.</ArchiveNotice>}
    </div>:<>
      {page.loading&&<p role="status">Loading file…</p>}{page.error&&<ArchiveNotice error>{page.error.message}</ArchiveNotice>}
      {page.data&&<pre tabIndex={0} className="min-h-0 overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-3 text-xs">{page.data.kind==='json'?JSON.stringify(page.data.content,null,2):(page.data.lines??[]).join('\n')}</pre>}
    </>}
    <DialogFooter>
      {image?<a className={buttonVariants({variant:'outline'})} href={api.downloadUrl(packageId,sceneId,file.file_id)} download={file.name.split('/').at(-1)}>Download PNG</a>:<>
        <Button variant="outline" disabled={offset===0||page.loading} onClick={()=>setOffset(0)}>First page</Button>
        <Button disabled={page.loading||!page.data||page.data.eof||page.data.next_offset==null} onClick={()=>{if(page.data?.next_offset!=null)setOffset(page.data.next_offset);}}>Next page</Button>
      </>}
      <DialogClose asChild><Button variant="outline">Close</Button></DialogClose>
    </DialogFooter>
  </DialogContent></Dialog>;
}
