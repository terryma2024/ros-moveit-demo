import { expect, test, vi } from 'vitest';
import { ArchiveError, ArchivesApiClient } from './archives-client';

test('archive requests encode ids, bounded query values and abort signal without paths or lease', async () => {
  const fetcher=vi.fn(async(_input: RequestInfo | URL,_init?: RequestInit)=>new Response('{}',{status:200}));
  const api=new ArchivesApiClient(fetcher);const controller=new AbortController();
  await api.packages('root ?&',true,controller.signal);
  await api.episodes('p?',{q:'frm',split:'train',outcome:'FAULT',sort:'-bytes',offset:100,limit:100});
  await api.file('p','scene','file',42,3);
  await api.startVerify('p');await api.cancelVerify('p');
  expect(fetcher.mock.calls[0]).toEqual(['/api/archives/packages?root_id=root+%3F%26&refresh=true',{signal:controller.signal}]);
  expect(fetcher.mock.calls[1][0]).toContain('p%3F/episodes?q=frm&split=train&outcome=FAULT&sort=-bytes&offset=100&limit=100');
  expect(fetcher.mock.calls[2][0]).toContain('/files/file?offset=42&limit=3');
  expect(JSON.stringify(fetcher.mock.calls)).not.toMatch(/lease|session_id|processing_output/);
  expect(api.frameUrl('p?','s&',4,'wrist')).toBe('/api/archives/packages/p%3F/episodes/s%26/frames/4/wrist');
});

test('structured errors are thrown and a failed HTTP response is never treated as data', async () => {
  const api=new ArchivesApiClient(async()=>new Response(JSON.stringify({code:'ARCHIVES_DISABLED',message:'No roots'}),{status:404}));
  await expect(api.config()).rejects.toMatchObject({code:'ARCHIVES_DISABLED',status:404});
  expect(new ArchiveError('X','message',413).message).toContain('message');
});
