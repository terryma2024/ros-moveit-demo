import { useEffect, useState } from 'react';
import type { ArchivesApiClient } from '@/api/archives-client';
import { Button } from '@/components/ui/button';
export function FramePlayer({api,packageId,sceneId,frameCount,row,onRowChange,rowTimes}:{api:ArchivesApiClient;packageId:string;sceneId:string;frameCount:number;row:number;onRowChange:(row:number)=>void;rowTimes:number[]}) {
  const [playing,setPlaying]=useState(false);
  const [failed,setFailed]=useState<string[]>([]);
  useEffect(()=>{setPlaying(false);},[packageId,sceneId]);
  useEffect(()=>{setFailed([]);},[packageId,sceneId,row]);
  useEffect(()=>{
    if(!playing) return;
    if(row>=frameCount-1){setPlaying(false);return;}
    const timer=setTimeout(()=>onRowChange(row+1),100);
    return ()=>clearTimeout(timer);
  },[playing,row,frameCount,onRowChange]);
  useEffect(()=>{
    const images:HTMLImageElement[]=[];
    for(let next=row+1;next<=Math.min(row+2,frameCount-1);next++) for(const camera of ['head','wrist'] as const){
      const image=new Image();image.src=api.frameUrl(packageId,sceneId,next,camera);images.push(image);
    }
    return ()=>images.forEach(image=>image.removeAttribute('src'));
  },[api,packageId,sceneId,row,frameCount]);
  if(!frameCount) return <p>No recorded frames for this scene.</p>;
  return <section className="space-y-3" aria-label="Camera playback"><div className="grid gap-3 md:grid-cols-2">{(['head','wrist'] as const).map(camera=><figure key={camera} className="rounded-lg border bg-card p-2"><figcaption className="mb-2 font-medium capitalize">{camera}</figcaption><img key={`${packageId}-${sceneId}-${row}`} alt={`${camera} camera`} className="w-full aspect-[4/3] object-contain bg-muted" loading="lazy" src={api.frameUrl(packageId,sceneId,row,camera)} onError={()=>setFailed(value=>[...value,camera])}/>{failed.includes(camera)&&<p role="status">{camera} frame unavailable at row {row}.</p>}</figure>)}</div><div className="flex items-center gap-3"><Button onClick={()=>{if(row>=frameCount-1) onRowChange(0);setPlaying(value=>!value);}}>{playing?'Pause':'Play'}</Button><input type="range" className="min-w-0 flex-1 accent-primary" aria-label="Episode row" min={0} max={frameCount-1} step={1} value={row} onChange={e=>{setPlaying(false);onRowChange(Number(e.target.value));}}/><span className="text-sm tabular-nums">Row {row} / {frameCount-1} · sim_time {rowTimes[row]??'—'} s</span></div></section>;
}
