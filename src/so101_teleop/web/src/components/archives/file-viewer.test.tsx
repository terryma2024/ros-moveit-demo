// @vitest-environment jsdom
import { fireEvent,render,screen } from '@testing-library/react';
import { expect,test } from 'vitest';
import { ArchivesApiClient } from '@/api/archives-client';
import { FileViewer } from './file-viewer';
import { detailData,episodeFetcher } from './test-fixtures';
test('JSON is formatted, audit next page uses server offset, last page disables next',async()=>{
  const api=new ArchivesApiClient(episodeFetcher);
  const {rerender}=render(<FileViewer api={api} packageId="p" sceneId="s" file={detailData.files[0]} onClose={()=>undefined}/>);
  expect(await screen.findByText(/"committed": false/)).toBeTruthy();
  rerender(<FileViewer key="audit" api={api} packageId="p" sceneId="s" file={detailData.files[1]} onClose={()=>undefined}/>);
  expect(await screen.findByText('first page')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Next page'}));
  expect(await screen.findByText('second page')).toBeTruthy();
  expect((screen.getByRole('button',{name:'Next page'}) as HTMLButtonElement).disabled).toBe(true);
});
test('oversized content gives a readable explanation',async()=>{
  const api=new ArchivesApiClient(async()=>new Response(JSON.stringify({code:'ARCHIVE_FILE_TOO_LARGE',message:'JSON exceeds 2 MiB'}),{status:413}));
  render(<FileViewer api={api} packageId="p" sceneId="s" file={detailData.files[0]} onClose={()=>undefined}/>);
  expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('2 MiB'));
});
