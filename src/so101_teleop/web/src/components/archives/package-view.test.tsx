// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ArchivesApiClient } from '@/api/archives-client';
import { PackageView } from './package-view';
import { fixtureFetcher, packageData } from './test-fixtures';
import { chooseSelect } from './select-test-utils';

test('statistics, all scene columns, filters, search and every sortable header',async()=>{
  const fetcher=vi.fn(fixtureFetcher);const onScene=vi.fn();
  render(<PackageView api={new ArchivesApiClient(fetcher)} packageId="p" onScene={onScene} />);
  expect(await screen.findByText('Scenes planned')).toBeTruthy();
  expect(await screen.findByRole('button',{name:'frm-000'})).toBeTruthy();
  expect(screen.getByRole('progressbar',{name:'Integrity verification'}).getAttribute('aria-valuenow')).toBe('0');
  const reason=screen.getByRole('button',{name:'Show reason for frm-000'});
  fireEvent.click(reason);
  expect(screen.getAllByText('Full preserved reason').length).toBeGreaterThan(0);
  await chooseSelect('Split','train');
  await chooseSelect('Outcome','VALID');
  fireEvent.change(screen.getByLabelText('Search scenes'),{target:{value:'frm-000'}});
  await waitFor(()=>expect(fetcher.mock.calls.some(([p])=>String(p).includes('q=frm-000')&&String(p).includes('split=train')&&String(p).includes('outcome=VALID'))).toBe(true));
  for(const header of screen.getAllByRole('button',{name:/^Sort /})) fireEvent.click(header);
  expect(screen.getAllByRole('button',{name:/^Sort /})).toHaveLength(12);
  fireEvent.click(await screen.findByRole('button',{name:'frm-000'}));expect(onScene).toHaveBeenCalledWith('frm-000');
  expect(screen.getAllByText('Full preserved reason').length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole('button',{name:'Verify integrity'}));
  await waitFor(()=>expect(fetcher.mock.calls.filter(([p,init])=>String(p).endsWith('/verify')&&init?.method==='POST')).toHaveLength(1));
  fireEvent.click(screen.getByRole('button',{name:'Verify integrity'}));
  await waitFor(()=>expect(fetcher.mock.calls.filter(([p,init])=>String(p).endsWith('/verify')&&init?.method==='POST')).toHaveLength(2));
});

test('supporting package shows seal metadata without episode entry',async()=>{
  const data={...packageData,package:{...packageData.package,kind:'supporting'},statistics:null};
  const fetcher=vi.fn(async()=>new Response(JSON.stringify(data),{status:200}));
  render(<PackageView api={new ArchivesApiClient(fetcher)} packageId="support" onScene={()=>undefined} />);
  expect(await screen.findByText(/Supporting package/)).toBeTruthy();
  expect(screen.queryByLabelText('Search scenes')).toBeNull();
  expect(fetcher.mock.calls).toHaveLength(1);
});

test('byte statistics use binary units, preserve exact bytes, and distinguish zero from unknown',async()=>{
  const data={...packageData,statistics:{...packageData.statistics!,episode_bytes:{total:4003116376,median:444904199 as number|null}}};
  const fetcher:typeof fetch=(path,init)=>String(path).endsWith('/packages/p')
    ?Promise.resolve(new Response(JSON.stringify(data)))
    :fixtureFetcher(path,init);
  const {unmount}=render(<PackageView api={new ArchivesApiClient(fetcher)} packageId="p" onScene={()=>undefined}/>);
  const label=await screen.findByText('Episode bytes total / median');
  const card=label.parentElement!;
  expect(within(card).getByText('3.73 GiB')).toHaveProperty('title','4003116376 bytes');
  expect(within(card).getByText('424.29 MiB')).toHaveProperty('title','444904199 bytes');
  unmount();
  data.statistics.episode_bytes={total:0,median:null};
  render(<PackageView api={new ArchivesApiClient(fetcher)} packageId="p" onScene={()=>undefined}/>);
  const empty=(await screen.findByText('Episode bytes total / median')).parentElement!;
  expect(within(empty).getByText('0 B')).toBeTruthy();
  expect(within(empty).getByText('—')).toBeTruthy();
});
