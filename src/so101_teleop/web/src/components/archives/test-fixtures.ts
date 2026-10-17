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
