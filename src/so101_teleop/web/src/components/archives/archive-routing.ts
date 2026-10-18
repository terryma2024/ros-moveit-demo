import { useEffect, useState } from 'react';
export type ArchiveSelection = { root?: string; pkg?: string; scene?: string };
function selectionFromUrl(): ArchiveSelection {
  const query = new URLSearchParams(location.search);
  return { root: query.get('root') || undefined, pkg: query.get('pkg') || undefined, scene: query.get('scene') || undefined };
}
export function archiveUrl(selection: ArchiveSelection) {
  const query = new URLSearchParams();
  for (const key of ['root', 'pkg', 'scene'] as const) if (selection[key]) query.set(key, selection[key]);
  return `/archives${query.size ? `?${query}` : ''}`;
}
export function useArchiveRouting() {
  const [selection, setSelection] = useState(selectionFromUrl);
  useEffect(() => {
    const pop = () => setSelection(selectionFromUrl());
    addEventListener('popstate', pop);
    return () => removeEventListener('popstate', pop);
  }, []);
  const choose = (value: ArchiveSelection) => { history.pushState({}, '', archiveUrl(value)); setSelection(value); };
  return { selection, choose };
}
