import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { ArchivesApiClient, EpisodeFilters, VerifyDto } from '@/api/archives-client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useArchiveRequest } from './use-archive-request';
import { ByteSize } from './byte-size';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { ArchiveSelect } from './archive-select';
import { ArchiveNotice } from './archive-feedback';

const columns = ['scene_id','split','collection_committed','outcome','reason','recording_attempt_count','final_recording_round','record_count','duration_s','bytes','teacher_result','qc_status'] as const;
const labels = ['Scene','Split','Committed','Outcome','Reason','Recording attempts','Final round','Rows','Duration (s)','Bytes','Teacher','QC'];
const emptyProgress: VerifyDto = {state:'idle',total:0,checked:0,mismatch_count:0,missing_count:0,issues:[],truncated:false};

export function PackageView({ api, packageId, onScene }: { api: ArchivesApiClient; packageId: string; onScene: (scene: string) => void }) {
  const request = useArchiveRequest(signal => api.package(packageId, signal), [api, packageId]);
  const [filters,setFilters] = useState<EpisodeFilters>({sort:'scene_id',offset:0,limit:100});
  const data = request.data;
  const rows = useArchiveRequest(signal => data?.statistics ? api.episodes(packageId, filters, signal) : null, [api, packageId, data, filters]);
  const [progress,setProgress] = useState<VerifyDto>(emptyProgress);
  const [verifyError,setVerifyError] = useState('');
  const [verifyAction,setVerifyAction] = useState<{kind:'start'|'cancel'}|null>(null);
  const [verifyBusy,setVerifyBusy] = useState(false);
  useEffect(() => { setFilters({sort:'scene_id',offset:0,limit:100}); setProgress(emptyProgress);setVerifyError('');setVerifyAction(null); },[packageId]);
  useEffect(() => {
    if (!data?.statistics) return;
    const controller = new AbortController();let active = true;let timer: ReturnType<typeof setTimeout>;
    setVerifyBusy(verifyAction !== null);
    const poll = async (first = false) => {
      try {
        const next = first && verifyAction?.kind === 'start' ? await api.startVerify(packageId,controller.signal) : first && verifyAction?.kind === 'cancel' ? await api.cancelVerify(packageId,controller.signal) : await api.verify(packageId,controller.signal);
        if (!active) return;
        setProgress(next);setVerifyBusy(false);
        if (next.state === 'running' || next.state === 'cancelling') timer = setTimeout(() => void poll(),500);
      } catch (error) { if (active) {setVerifyError(String(error));setVerifyBusy(false);} }
    };
    void poll(true);
    return () => { active=false;controller.abort();clearTimeout(timer); };
  },[api,packageId,data,verifyAction]);
  const filter = (change: EpisodeFilters) => setFilters(current=>({...current,...change,offset:0}));
  if (request.error) return <ArchiveNotice error>{request.error.message}</ArchiveNotice>;
  if (!data) return <p role="status">Loading package…</p>;
  const stats=data.statistics;
  return <section className="space-y-4" aria-label="Package details">
    <h2 className="text-xl font-semibold">{data.package.name}</h2>
    <Card className="p-4 text-sm break-words"><CardHeader><h3 className="font-semibold">Seal metadata</h3></CardHeader><CardContent><dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">{Object.entries(data.seal).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{key==='bytes'&&typeof value==='number'?<ByteSize value={value}/>:String(value??'Unavailable')}</dd></div>)}</dl></CardContent></Card>
    {data.warnings?.map((warning,i)=><ArchiveNotice key={i}>{warning}</ArchiveNotice>)}
    <Card className="p-4"><dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(data.identity).map(([key,item])=><div key={key}><dt className="text-sm text-muted-foreground">{key}</dt><dd className="break-all">{String(item.value??'Unavailable')}{item.source&&<small className="block text-muted-foreground">{item.source}</small>}</dd></div>)}</dl></Card>
    {!stats ? <p>Supporting package — seal metadata only.</p> : <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{([
        ['Scenes planned',stats.planned],['Collection committed',stats.committed],['Recording retry rounds run',stats.retry_rounds_run],['Recovered by retry',stats.recovered],
        ['Rows total / median',`${stats.duration_rows.total} / ${stats.duration_rows.median??'—'}`],['Duration total / median (s)',`${stats.duration_seconds.total} / ${stats.duration_seconds.median??'—'}`],['Episode bytes total / median',<span><ByteSize value={stats.episode_bytes.total}/> / <ByteSize value={stats.episode_bytes.median}/></span>],
      ] as const).map(([label,value])=><Card key={label} className="p-4"><div className="text-sm text-muted-foreground">{label}</div><div className="text-xl font-semibold">{value}</div></Card>)}</div>
      <div className="flex flex-wrap gap-4 text-sm"><span>Committed splits: {Object.entries(stats.committed_by_split).map(([k,v])=>`${k} ${v}`).join(' · ')}</span><span>Not committed: {Object.entries(stats.non_committed_by_outcome).map(([k,v])=>`${k} ${v}`).join(' · ')}</span><span>Recovered by round: {JSON.stringify(stats.recovered_by_round)}</span></div>
      <Card className="p-4 space-y-3"><div className="flex flex-wrap items-center gap-3"><Button disabled={verifyBusy||progress.state==='running'||progress.state==='cancelling'} onClick={()=>{setVerifyError('');setVerifyAction({kind:'start'});}}>Verify integrity</Button><Button variant="outline" disabled={verifyBusy||!['running','cancelling'].includes(progress.state)} onClick={()=>setVerifyAction({kind:'cancel'})}>Cancel verification</Button><span role="status"><Badge variant="outline">{progress.state}</Badge>: {progress.checked}/{progress.total} · mismatches {progress.mismatch_count} · missing {progress.missing_count}</span></div><Progress aria-label="Integrity verification" value={progress.total>0?Math.min(100,progress.checked/progress.total*100):0}/>{verifyError&&<ArchiveNotice error>{verifyError}</ArchiveNotice>}{progress.issues?.map((issue,i)=><p key={i} className="text-sm break-all">{issue.name}: {issue.kind} — {issue.message}</p>)}{progress.truncated&&<p>Only the first 100 issues are shown.</p>}</Card>
      <div className="flex flex-wrap gap-3 items-end">
        <ArchiveSelect label="Split" value={filters.split??'__all__'} onValueChange={value=>filter({split:(value==='__all__'?undefined:value) as EpisodeFilters['split']})} options={[{value:'__all__',label:'All splits'},...['train','validation','offline_test'].map(value=>({value,label:value}))]}/>
        <ArchiveSelect label="Outcome" value={filters.outcome??'__all__'} onValueChange={value=>filter({outcome:(value==='__all__'?undefined:value) as EpisodeFilters['outcome']})} options={[{value:'__all__',label:'All outcomes'},...['VALID','INVALID','FAULT','MISSING'].map(value=>({value,label:value}))]}/>
        <div className="space-y-2"><Label htmlFor="archive-scene-search">Search scenes</Label><Input id="archive-scene-search" aria-label="Search scenes" maxLength={128} value={filters.q??''} onChange={e=>filter({q:e.target.value})}/></div>
      </div>
      {rows.error&&<ArchiveNotice error>{rows.error.message}</ArchiveNotice>}{rows.loading&&<p role="status">Loading scenes…</p>}
      <div className="overflow-x-auto rounded-lg border"><Table><TableHeader><TableRow>{columns.map((key,i)=><TableHead key={key} aria-sort={filters.sort?.replace('-','')===key?(filters.sort.startsWith('-')?'descending':'ascending'):'none'}><Button variant="ghost" size="sm" className="whitespace-nowrap" aria-label={`Sort ${labels[i]}`} onClick={()=>filter({sort:filters.sort===key?`-${key}`:key})}>{labels[i]} {filters.sort?.replace('-','')===key?(filters.sort.startsWith('-')?'↓':'↑'):''}</Button></TableHead>)}</TableRow></TableHeader><TableBody>{rows.data?.episodes.map(row=><TableRow key={row.scene_id}>{columns.map(key=><TableCell key={key}>{key==='scene_id'?<Button variant="link" onClick={()=>onScene(row.scene_id)}>{row.scene_id}</Button>:key==='bytes'?<ByteSize value={row.bytes}/>:key==='reason'&&row.reason?<Collapsible><CollapsibleTrigger asChild><Button variant="ghost" size="sm" className="group max-w-48 justify-start gap-1" aria-label={`Show reason for ${row.scene_id}`} title={row.reason}><span className="min-w-0 truncate">{row.reason}</span><ChevronDown aria-hidden="true" className="h-4 w-4 shrink-0 transition-transform group-aria-expanded:rotate-180"/></Button></CollapsibleTrigger><CollapsibleContent className="max-w-sm whitespace-pre-wrap break-words">{row.reason}</CollapsibleContent></Collapsible>:['outcome','qc_status','teacher_result'].includes(key)&&row[key]?<Badge variant={['FAULT','INVALID','FAIL','FAILED'].includes(String(row[key]))?'destructive':'outline'}>{String(row[key])}</Badge>:String(row[key]??'—')}</TableCell>)}</TableRow>)}</TableBody></Table></div>
      <div className="flex flex-wrap gap-3 items-center"><Button variant="outline" disabled={!filters.offset} onClick={()=>setFilters(f=>({...f,offset:Math.max(0,(f.offset??0)-100)}))}>Previous scenes</Button><span>{rows.data?.total??0} scenes · offset {filters.offset??0}</span><Button variant="outline" disabled={(filters.offset??0)+100>=(rows.data?.total??0)} onClick={()=>setFilters(f=>({...f,offset:(f.offset??0)+100}))}>Next scenes</Button></div>
    </>}
  </section>;
}
