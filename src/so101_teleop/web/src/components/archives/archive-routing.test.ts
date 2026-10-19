// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { expect, test } from 'vitest';
import { archiveUrl, useArchiveRouting } from './archive-routing';

test('query selections are shareable, encoded, and follow browser history',()=>{
  history.replaceState({},'', '/archives?root=r&pkg=p&scene=frm-000');
  const {result}=renderHook(useArchiveRouting);
  expect(result.current.selection).toEqual({root:'r',pkg:'p',scene:'frm-000'});
  act(()=>result.current.choose({root:'r2'}));
  expect(location.search).toBe('?root=r2');
  expect(result.current.selection.pkg).toBeUndefined();
  act(()=>{history.replaceState({},'','/archives?root=r&pkg=p&scene=frm-000');dispatchEvent(new PopStateEvent('popstate'));});
  expect(result.current.selection.scene).toBe('frm-000');
  expect(archiveUrl({root:'r ?',pkg:'p'})).toBe('/archives?root=r+%3F&pkg=p');
});
