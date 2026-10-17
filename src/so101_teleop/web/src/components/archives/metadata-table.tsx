import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ByteSize } from './byte-size';

type Fields = Record<string, unknown> | unknown[];
type FileEntry = { size: number; sha256: string };
const pageSize = 50;
const isFields = (value: unknown): value is Fields => value !== null && typeof value === 'object';
const isFile = (value: unknown): value is FileEntry => isFields(value)
  && !Array.isArray(value) && Object.keys(value).length === 2
  && typeof value.size === 'number' && typeof value.sha256 === 'string';

function Value({ name, value }: { name: string; value: unknown }) {
  const [expanded, setExpanded] = useState(false);
  if (!isFields(value)) {
    if (typeof value === 'number' && (name === 'bytes' || name.endsWith('_bytes'))) return <ByteSize value={value}/>;
    return <span>{value === '' ? '""' : String(value)}</span>;
  }
  const count = Object.keys(value).length;
  if (!count) return <span>{name}: {Array.isArray(value) ? 'Empty array' : 'Empty object'}</span>;
  return <div className="min-w-0 space-y-2">
    <Button variant="outline" size="sm" className="h-auto max-w-full whitespace-normal break-all text-left py-1"
      aria-expanded={expanded} onClick={()=>setExpanded(current=>!current)}>
      {expanded ? 'Collapse' : 'Expand'} {name} ({count} {count === 1 ? 'entry' : 'entries'})
    </Button>
    {expanded&&<MetadataTable values={value} label={name}/>}
  </div>;
}

export function MetadataTable({ values, label = 'Metadata' }: { values: Fields; label?: string }) {
  const [page, setPage] = useState(0);
  const entries = Object.entries(values);
  const files = entries.length > 0 && entries.every(([,value])=>isFile(value));
  const last = Math.max(0, Math.ceil(entries.length / pageSize) - 1);
  const start = page * pageSize;
  return <div className="min-w-0 space-y-2">
    <Table aria-label={`${label} ${files ? 'list' : 'fields'}`} className="table-fixed text-sm">
      <TableHeader><TableRow>
        <TableHead className={files ? 'w-2/5' : 'w-1/3'}>{files ? 'File' : 'Field'}</TableHead>
        <TableHead className={files ? 'w-1/5 whitespace-normal break-all' : ''}>{files ? 'Size' : 'Value'}</TableHead>
        {files&&<TableHead>SHA256</TableHead>}
      </TableRow></TableHeader>
      <TableBody>{entries.slice(start,start+pageSize).map(([name,value])=>{
        if (files&&isFile(value)) return <TableRow key={name}>
          <TableCell className="align-top whitespace-normal break-all font-medium">{name}</TableCell>
          <TableCell className="align-top whitespace-normal break-all"><ByteSize value={value.size}/></TableCell>
          <TableCell className="align-top whitespace-normal break-all text-xs">{value.sha256}</TableCell>
        </TableRow>;
        if (isFields(value)) return <TableRow key={name}>
          <TableCell colSpan={2} className="align-top whitespace-normal break-all"><Value name={name} value={value}/></TableCell>
        </TableRow>;
        return <TableRow key={name}>
          <TableCell className="align-top whitespace-normal break-all font-medium">{name}</TableCell>
          <TableCell className="align-top whitespace-normal break-all"><Value name={name} value={value}/></TableCell>
        </TableRow>;
      })}</TableBody>
    </Table>
    {last>0&&<div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground" aria-live="polite">Rows {start+1}–{Math.min(start+pageSize,entries.length)} of {entries.length}</span>
      <Button variant="outline" size="sm" disabled={page===0} onClick={()=>setPage(0)}>First page</Button>
      <Button variant="outline" size="sm" disabled={page===0} onClick={()=>setPage(current=>current-1)}>Previous page</Button>
      <Button variant="outline" size="sm" disabled={page===last} onClick={()=>setPage(current=>current+1)}>Next page</Button>
      <Button variant="outline" size="sm" disabled={page===last} onClick={()=>setPage(last)}>Last page</Button>
    </div>}
  </div>;
}
