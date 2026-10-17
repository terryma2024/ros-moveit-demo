// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ArchivesApiClient } from '@/api/archives-client';
import { ArchiveBrowser } from './archive-browser';
import { fixtureFetcher } from './test-fixtures';

test('lists packages, opens URL-selected package, root switch clears package and scene',async()=>{
  history.replaceState({},'','/archives?root=r&pkg=p');
  const fetcher=vi.fn(fixtureFetcher);
  render(<ArchiveBrowser api={new ArchivesApiClient(fetcher)} />);
  expect(await screen.findByText('Scenes planned')).toBeTruthy();
  expect(screen.getByText('source_commit')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Search root'),{target:{value:'r2'}});
  await waitFor(()=>expect(location.search).toBe('?root=r2'));
  expect(await screen.findByRole('button',{name:'Open Synthetic collection'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Refresh packages'}));
  await waitFor(()=>expect(fetcher.mock.calls.some(([p])=>String(p).includes('refresh=true'))).toBe(true));
});

test('disabled archives show an understandable state',async()=>{
  const api=new ArchivesApiClient(async()=>new Response(JSON.stringify({code:'ARCHIVES_DISABLED',message:'No roots configured'}),{status:404}));
  render(<ArchiveBrowser api={api} />);
  expect(await screen.findByText(/Archives are not enabled/)).toBeTruthy();
});
