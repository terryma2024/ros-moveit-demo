import { useId } from 'react';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export function ArchiveSelect({label,value,options,onValueChange}:{label:string;value:string;options:{value:string;label:string}[];onValueChange:(value:string)=>void}) {
  const id=useId();
  return <div className="min-w-0 space-y-2">
    <Label htmlFor={id}>{label}</Label>
    <Select value={value} onValueChange={onValueChange} disabled={!options.length}>
      <SelectTrigger id={id} aria-label={label} className="w-full min-w-[10rem] max-w-full"><SelectValue placeholder="Choose a root"/></SelectTrigger>
      <SelectContent position="popper">{options.map(option=><SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
    </Select>
  </div>;
}
