// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { ArchivesApiClient } from '@/api/archives-client';
import { ArchiveBrowser } from './archive-browser';
import { episodeFetcher, detailData } from './test-fixtures';

test('scene deep link opens summary, timeline and slider synchronizes two frames and SVG cursors',async()=>{
  history.replaceState({},'','/archives?root=r&pkg=p&scene=frm-000');
  render(<ArchiveBrowser api={new ArchivesApiClient(episodeFetcher)} />);
  expect(await screen.findByRole('heading',{name:'Episode frm-000'})).toBeTruthy();
  expect(screen.getByRole('heading',{name:'Recording and processing attempts'})).toBeTruthy();
  fireEvent.change(screen.getByRole('slider',{name:'Episode row'}),{target:{value:'4'}});
  expect(screen.getByAltText('head camera').getAttribute('src')).toContain('/frames/4/head');
  expect(screen.getByAltText('wrist camera').getAttribute('src')).toContain('/frames/4/wrist');
  expect(screen.getByText(/Row 4.*36.6/)).toBeTruthy();
  for(const cursor of screen.getAllByTestId('signal-cursor')) expect(cursor.getAttribute('data-row')).toBe('4');
  expect(screen.getAllByRole('img',{name:/signals/})).toHaveLength(2);
});

test('rapid scene switch ignores late detail response even when fetch ignores abort',async()=>{
  let resolveOld!: (value:Response)=>void;
  const old=new Promise<Response>(resolve=>{resolveOld=resolve;});
  const api=new ArchivesApiClient((path,init)=>String(path).endsWith('/episodes/old')?old:episodeFetcher(path,init));
  history.replaceState({},'','/archives?root=r&pkg=p&scene=old');
  render(<ArchiveBrowser api={api} />);
  await waitFor(()=>expect(screen.getByText(/Loading episode/)).toBeTruthy());
  act(()=>{history.replaceState({},'','/archives?root=r&pkg=p&scene=frm-000');dispatchEvent(new PopStateEvent('popstate'));});
  expect(await screen.findByRole('heading',{name:'Episode frm-000'})).toBeTruthy();
  await act(async()=>resolveOld(new Response(JSON.stringify({...detailData,scene_id:'old'}))));
  expect(screen.queryByRole('heading',{name:'Episode old'})).toBeNull();
});

test('manifest PNG names download the selected file without opening the JSON viewer',async()=>{
  history.replaceState({},'','/archives?root=r&pkg=p&scene=frm-000');
  const name='episode/frames/000000-head.png';
  const api=new ArchivesApiClient((path,init)=>String(path).endsWith('/episodes/frm-000')
    ?Promise.resolve(new Response(JSON.stringify({...detailData,files:[...detailData.files,{file_id:'head image',name,bytes:42,sha256:'abc'}]})))
    :episodeFetcher(path,init));
  render(<ArchiveBrowser api={api} />);
  const link=await screen.findByRole('link',{name});
  expect(link.getAttribute('href')).toBe('/api/archives/packages/p/episodes/frm-000/files/head%20image/download');
  expect(link.getAttribute('download')).toBe('000000-head.png');
  expect(link.closest('button')).toBeNull();
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.getByRole('button',{name:'episode/seal.json'})).toBeTruthy();
});

test('manifest pages bound visible files and keep the final JSON and PNG accessible',async()=>{
  history.replaceState({},'','/archives?root=r&pkg=p&scene=frm-000');
  const files=Array.from({length:99},(_,i)=>({file_id:`file-${i}`,name:`file-${i}.bin`,bytes:i,sha256:`hash-${i}`}));
  files.push({file_id:'seal',name:'episode/seal.json',bytes:123,sha256:'seal-hash'},
    {file_id:'last image',name:'frames/last.png',bytes:60898,sha256:'last-hash'});
  const api=new ArchivesApiClient((path,init)=>String(path).endsWith('/episodes/frm-000')
    ?Promise.resolve(new Response(JSON.stringify({...detailData,files})))
    :episodeFetcher(path,init));
  render(<ArchiveBrowser api={api} />);
  const manifest=within(await screen.findByRole('region',{name:'Manifest files'}));
  expect(manifest.getByRole('combobox',{name:'Rows per page'}).textContent).toBe('50');
  expect(manifest.getAllByRole('row')).toHaveLength(51);
  expect(manifest.getByText('1–50 of 101 files · Page 1 of 3')).toBeTruthy();
  expect((manifest.getByRole('button',{name:'Previous page'}) as HTMLButtonElement).disabled).toBe(true);
  expect(manifest.queryByText('file-50.bin')).toBeNull();
  fireEvent.click(manifest.getByRole('button',{name:'Next page'}));
  expect(manifest.getByText('file-50.bin')).toBeTruthy();
  expect(manifest.queryByText('file-0.bin')).toBeNull();
  fireEvent.click(manifest.getByRole('button',{name:'episode/seal.json'}));
  expect(await screen.findByRole('dialog')).toBeTruthy();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Close'}));
  fireEvent.click(manifest.getByRole('button',{name:'Last page'}));
  expect(manifest.getAllByRole('row')).toHaveLength(2);
  expect(manifest.getByText('101–101 of 101 files · Page 3 of 3')).toBeTruthy();
  const link=manifest.getByRole('link',{name:'frames/last.png'});
  expect(link.getAttribute('href')).toContain('/files/last%20image/download');
  expect(link.getAttribute('download')).toBe('last.png');
  expect(manifest.getByTitle('60898 bytes').textContent).toBe('59.47 KiB');
  expect(manifest.getByText('last-hash')).toBeTruthy();
  expect((manifest.getByRole('button',{name:'Next page'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(manifest.getByRole('button',{name:'Previous page'}));
  expect(manifest.getByText('file-50.bin')).toBeTruthy();
  fireEvent.click(manifest.getByRole('button',{name:'First page'}));
  expect(manifest.getByText('file-0.bin')).toBeTruthy();
});

test('large seal and QC metadata stay out of the overview and remain accessible through paged nested tables',async()=>{
  history.replaceState({},'','/archives?root=r&pkg=p&scene=frm-000');
  const files=Object.fromEntries(Array.from({length:1000},(_,row)=>[`frames/${row}-head.png`,{sha256:`hash-${row}`,size:60000}]));
  const seal={...detailData.seal,record_count:1000,files};
  const qc={status:'PASS',counts:{records:1000},checks:{reference:{details:{first:'preserved-first',last:'preserved-last'}}}};
  const api=new ArchivesApiClient((path,init)=>String(path).endsWith('/episodes/frm-000')
    ?Promise.resolve(new Response(JSON.stringify({...detailData,seal,qc_summary:qc})))
    :episodeFetcher(path,init));
  render(<ArchiveBrowser api={api} />);
  const sealButton=await screen.findByRole('button',{name:'View full Episode seal'});
  expect(screen.queryByText(/frames\/999-head.png/)).toBeNull();
  expect(screen.queryByText(/preserved-last/)).toBeNull();
  expect(screen.getByText('record_count')).toBeTruthy();
  fireEvent.click(sealButton);
  let dialog=screen.getByRole('dialog',{name:'Episode seal: full metadata'});
  expect(within(dialog).getByRole('table',{name:'Metadata fields'})).toBeTruthy();
  expect(dialog.querySelector('pre')).toBeNull();
  expect(within(dialog).getByText('false')).toBeTruthy();
  fireEvent.click(within(dialog).getByRole('button',{name:/^Expand files/}));
  expect(await within(dialog).findByText('frames/0-head.png')).toBeTruthy();
  expect(within(dialog).queryByText('frames/999-head.png')).toBeNull();
  fireEvent.click(within(dialog).getByRole('button',{name:'Last page'}));
  expect(within(dialog).getByText('frames/999-head.png')).toBeTruthy();
  expect(within(dialog).getByText('hash-999')).toBeTruthy();
  expect(within(dialog).getAllByTitle('60000 bytes')[0].textContent).toBe('58.59 KiB');
  fireEvent.click(within(dialog).getByRole('button',{name:'Close'}));
  expect(screen.queryByRole('dialog')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'View full QC summary'}));
  dialog=screen.getByRole('dialog',{name:'QC summary: full metadata'});
  for(const name of ['checks','reference','details']) {
    fireEvent.click(await within(dialog).findByRole('button',{name:new RegExp(`^Expand ${name}`)}));
  }
  expect(within(dialog).getByText('preserved-first')).toBeTruthy();
  expect(within(dialog).getByText('preserved-last')).toBeTruthy();
});
