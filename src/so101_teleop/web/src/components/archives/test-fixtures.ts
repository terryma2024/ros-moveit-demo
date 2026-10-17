import type { PackageViewDto, EpisodePageDto } from '@/api/archives-client';
export const packageInfo={package_id:'p',name:'Synthetic collection',kind:'collection' as const,files:4,bytes:123,registered:true,manifest_sha256:'abc',reason:'test',sealed_at:'2026-10-17'};
export const packageData: PackageViewDto={package:packageInfo,seal:{kind:'SEALED_EVIDENCE_ROOT',files:4,bytes:123},identity:{source_commit:{value:null,source:null}},warnings:[],statistics:{planned:4,committed:2,non_committed_by_outcome:{FAULT:1,MISSING:1,INVALID:0},committed_by_split:{train:1,validation:1,offline_test:0},retry_rounds_run:1,recovered:1,recovered_by_round:{'1':1},duration_rows:{total:12,median:6},duration_seconds:{total:1.2,median:0.6},episode_bytes:{total:123,median:61.5}}};
export const episodePage: EpisodePageDto={total:1,episodes:[{scene_id:'frm-000',split:'train',collection_committed:true,outcome:'VALID',reason:'Full preserved reason',recording_attempt_count:2,final_recording_round:1,record_count:5,duration_s:0.5,bytes:123,teacher_result:'PASS',qc_status:'PASS'}]};
export const idle={state:'idle',total:0,checked:0,mismatch_count:0,missing_count:0,issues:[],truncated:false};
export function fixtureFetcher(path: RequestInfo | URL, _init?: RequestInit): Promise<Response> {
  const url=String(path);let data: unknown={};
  if(url.endsWith('/config')) data={enabled:true,roots:[{root_id:'r',label:'Registry'},{root_id:'r2',label:'Other'}]};
  else if(url.includes('/packages?')) data={packages:[packageInfo],warnings:[]};
  else if(url.includes('/episodes?')) data=episodePage;
  else if(url.endsWith('/verify')) data=idle;
  else data=packageData;
  return Promise.resolve(new Response(JSON.stringify(data),{status:200}));
}
export const detailData={scene_id:'frm-000',scene:{seed:200,split:'train',cup_position_world_m:[0.1,0.2,0.3]},collection_committed:true,seal:{status:'PASSED',committed:false},processed_result:{act_data_status:'VALID',proc_attempt:1},qc_summary:{status:'PASS'},attempts:[{kind:'recording',round:0,wave:0,shard:'w00',outcome:'VALID',reason:null}],files:[{file_id:'seal',name:'episode/seal.json',bytes:123,sha256:'abc'},{file_id:'audit',name:'episode/audit/events.jsonl',bytes:222,sha256:'def'}],frame_count:5,warnings:[]};
export const seriesData={points:[0,4].map(row=>({row,t:36.2+row/10,action:[row,row,row,row,row,row],state:Array(8).fill(row) as number[]})),row_times_s:[36.2,36.3,36.4,36.5,36.6],stride:4};
export function episodeFetcher(path: RequestInfo | URL, init?:RequestInit): Promise<Response> {
  const url=String(path);
  if(url.endsWith('/series')) return Promise.resolve(new Response(JSON.stringify(seriesData)));
  if(url.endsWith('/episodes/frm-000')) return Promise.resolve(new Response(JSON.stringify(detailData)));
  if(url.includes('/files/seal')) return Promise.resolve(new Response(JSON.stringify({kind:'json',content:detailData.seal,eof:true})));
  if(url.includes('/files/audit')) return Promise.resolve(new Response(JSON.stringify({kind:'jsonl',lines:[url.includes('offset=37')?'second page':'first page'],next_offset:url.includes('offset=37')?null:37,eof:url.includes('offset=37')})));
  return fixtureFetcher(path,init);
}
