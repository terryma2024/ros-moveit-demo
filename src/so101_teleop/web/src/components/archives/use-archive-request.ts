import { useEffect, useState, type DependencyList } from 'react';
export function useArchiveRequest<T>(load: (signal: AbortSignal) => Promise<T> | null, dependencies: DependencyList) {
  const [result, setResult] = useState<{ data?: T; error?: Error; loading: boolean }>({ loading: true });
  useEffect(() => {
    const controller = new AbortController();let active = true;
    setResult({ loading: true });
    const promise = load(controller.signal);
    if (promise === null) setResult({ loading: false });
    else void promise.then(data => { if (active) setResult({ data, loading: false }); }, error => { if (active) setResult({ error, loading: false }); });
    return () => { active = false; controller.abort(); };
  }, dependencies);
  return result;
}
