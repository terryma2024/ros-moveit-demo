import { Card } from '@/components/ui/card';
import { ArchiveEmpty } from './archive-feedback';
import type { EpisodeSeriesDto } from '@/api/archives-client';
const colors=['hsl(var(--primary))','hsl(var(--destructive))','#16a34a','#a855f7','#d97706','#0891b2','#ec4899','#64748b'];
export function SignalChart({points,group,currentRow,currentTime}:{points:EpisodeSeriesDto['points'];group:'action'|'state';currentRow:number;currentTime:number|undefined}) {
  const dimensions=Math.max(0,...points.map(p=>p[group].length));
  if(!points.length) return <ArchiveEmpty>No {group} signals.</ArchiveEmpty>;
  const times=points.map(p=>p.t);const values=points.flatMap(p=>p[group]);
  const minT=Math.min(...times),maxT=Math.max(...times);
  const minY=Math.min(...values),maxY=Math.max(...values);
  const x=(t:number)=>40+(t-minT)/(maxT-minT||1)*560;
  const y=(v:number)=>170-(v-minY)/(maxY-minY||1)*145;
  return <Card className="p-3"><h3 className="font-semibold capitalize">{group} signals</h3><svg role="img" aria-label={`${group} signals`} viewBox="0 0 640 200" className="w-full"><line x1={40} y1={170} x2={600} y2={170} stroke="currentColor" opacity="0.3"/><text x={40} y={192} fill="currentColor" fontSize="11">{minT.toFixed(2)} s</text><text x={550} y={192} fill="currentColor" fontSize="11">{maxT.toFixed(2)} s</text><text x={0} y={30} fill="currentColor" fontSize="10">{maxY.toFixed(2)}</text><text x={0} y={170} fill="currentColor" fontSize="10">{minY.toFixed(2)}</text>{Array.from({length:dimensions},(_,dimension)=><polyline key={dimension} fill="none" stroke={colors[dimension%colors.length]} strokeWidth="1.5" points={points.filter(p=>p[group][dimension]!==undefined).map(p=>`${x(p.t)},${y(p[group][dimension])}`).join(' ')}/>)}{currentTime!==undefined&&<line data-testid="signal-cursor" data-row={currentRow} data-time={currentTime} x1={x(currentTime)} x2={x(currentTime)} y1={20} y2={170} stroke="currentColor" strokeDasharray="4 3"/>}</svg><div className="flex flex-wrap gap-3 text-xs">{Array.from({length:dimensions},(_,dimension)=><span key={dimension} style={{color:colors[dimension%colors.length]}}>{group}[{dimension}]</span>)}</div></Card>;
}
