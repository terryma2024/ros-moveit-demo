// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
