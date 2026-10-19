import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { Button } from './button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './table';

// shadcn's Tailwind 3 Data Table pattern: https://v3.shadcn.com/docs/components/data-table
export function DataTable<TData>({columns,data,getRowId,label}: {
  columns:ColumnDef<TData>[];
  data:TData[];
  getRowId:(row:TData)=>string;
  label:string;
}) {
  const table=useReactTable({
    data,columns,getRowId,
    getCoreRowModel:getCoreRowModel(),
    getPaginationRowModel:getPaginationRowModel(),
    initialState:{pagination:{pageIndex:0,pageSize:50}},
  });
  const {pageIndex,pageSize}=table.getState().pagination;
  const total=table.getRowCount();
  return <div className="space-y-3">
    <div className="rounded-md border [&_[data-slot=table-container]]:max-h-[32rem]">
      <Table aria-label={label} className="min-w-[40rem] table-fixed">
        <TableHeader className="sticky top-0 z-10 bg-background">
          {table.getHeaderGroups().map(group=><TableRow key={group.id}>
            {group.headers.map(header=><TableHead key={header.id} style={{width:`${header.getSize()/table.getTotalSize()*100}%`}}>
              {header.isPlaceholder?null:flexRender(header.column.columnDef.header,header.getContext())}
            </TableHead>)}
          </TableRow>)}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.length?table.getRowModel().rows.map(row=><TableRow key={row.id}>
            {row.getVisibleCells().map(cell=><TableCell key={cell.id} className="whitespace-normal break-all">
              {flexRender(cell.column.columnDef.cell,cell.getContext())}
            </TableCell>)}
          </TableRow>):<TableRow><TableCell colSpan={columns.length} className="h-24 text-center">No manifest files.</TableCell></TableRow>}
        </TableBody>
      </Table>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p aria-live="polite" className="text-sm text-muted-foreground">{total?pageIndex*pageSize+1:0}–{Math.min((pageIndex+1)*pageSize,total)} of {total} files · Page {pageIndex+1} of {Math.max(1,table.getPageCount())}</p>
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Rows per page</span>
          <Select value={String(pageSize)} onValueChange={value=>table.setPageSize(Number(value))}>
            <SelectTrigger aria-label="Rows per page" size="sm" className="w-[75px]"><SelectValue/></SelectTrigger>
            <SelectContent side="top">{[10,20,30,40,50,100].map(size=><SelectItem key={size} value={String(size)}>{size}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <nav aria-label={`${label} pagination`} className="flex items-center gap-2">
          <Button variant="outline" size="icon" className="h-8 w-8" disabled={!table.getCanPreviousPage()} onClick={()=>table.setPageIndex(0)}><ChevronsLeft aria-hidden="true" className="h-4 w-4"/><span className="sr-only">First page</span></Button>
          <Button variant="outline" size="icon" className="h-8 w-8" disabled={!table.getCanPreviousPage()} onClick={()=>table.previousPage()}><ChevronLeft aria-hidden="true" className="h-4 w-4"/><span className="sr-only">Previous page</span></Button>
          <Button variant="outline" size="icon" className="h-8 w-8" disabled={!table.getCanNextPage()} onClick={()=>table.nextPage()}><ChevronRight aria-hidden="true" className="h-4 w-4"/><span className="sr-only">Next page</span></Button>
          <Button variant="outline" size="icon" className="h-8 w-8" disabled={!table.getCanNextPage()} onClick={()=>table.setPageIndex(Math.max(0,table.getPageCount()-1))}><ChevronsRight aria-hidden="true" className="h-4 w-4"/><span className="sr-only">Last page</span></Button>
        </nav>
      </div>
    </div>
  </div>;
}
