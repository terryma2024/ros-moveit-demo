import type { components, paths } from './unified-schema';
type Schemas = components['schemas'];
export type ArchiveConfigDto = Schemas['ArchiveConfigView'];
export type PackageListDto = Schemas['PackageList'];
export type PackageViewDto = Schemas['PackageView'];
export type EpisodePageDto = Schemas['EpisodePage'];
export type EpisodeDetailDto = Schemas['EpisodeDetail'];
export type EpisodeSeriesDto = Schemas['EpisodeSeries'];
export type FileViewDto = Schemas['FileView'];
export type VerifyDto = Schemas['VerifyProgress'];
export type EpisodeFilters = NonNullable<paths['/api/archives/packages/{package_id}/episodes']['get']['parameters']['query']>;
export class ArchiveError extends Error {
  constructor(public code: string, message: string, public status: number) { super(`${code}: ${message}`); }
}
const id = encodeURIComponent;
const base = '/api/archives';
export class ArchivesApiClient {
  constructor(private fetcher: typeof fetch = (input, init) => fetch(input, init)) {}
  private async json<T>(url: string, signal?: AbortSignal, method?: string): Promise<T> {
    const response = await this.fetcher(url, method ? { signal, method } : { signal });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new ArchiveError(data?.code ?? `HTTP_${response.status}`, data?.message ?? 'Archive request failed', response.status);
    return data as T;
  }
  config(signal?: AbortSignal) { return this.json<ArchiveConfigDto>(`${base}/config`, signal); }
  packages(root: string, refresh = false, signal?: AbortSignal) {
    return this.json<PackageListDto>(`${base}/packages?${new URLSearchParams({ root_id: root, refresh: String(refresh) })}`, signal);
  }
  package(pkg: string, signal?: AbortSignal) { return this.json<PackageViewDto>(`${base}/packages/${id(pkg)}`, signal); }
  episodes(pkg: string, filters: EpisodeFilters = {}, signal?: AbortSignal) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
    return this.json<EpisodePageDto>(`${base}/packages/${id(pkg)}/episodes?${query}`, signal);
  }
  private episode(pkg: string, scene: string) { return `${base}/packages/${id(pkg)}/episodes/${id(scene)}`; }
  detail(pkg: string, scene: string, signal?: AbortSignal) { return this.json<EpisodeDetailDto>(this.episode(pkg, scene), signal); }
  series(pkg: string, scene: string, signal?: AbortSignal) { return this.json<EpisodeSeriesDto>(`${this.episode(pkg, scene)}/series`, signal); }
  frameUrl(pkg: string, scene: string, row: number, camera: 'head' | 'wrist') { return `${this.episode(pkg, scene)}/frames/${row}/${camera}`; }
  file(pkg: string, scene: string, file: string, offset = 0, limit = 100, signal?: AbortSignal) {
    return this.json<FileViewDto>(`${this.episode(pkg, scene)}/files/${id(file)}?${new URLSearchParams({ offset: String(offset), limit: String(limit) })}`, signal);
  }
  startVerify(pkg: string, signal?: AbortSignal) { return this.json<VerifyDto>(`${base}/packages/${id(pkg)}/verify`, signal, 'POST'); }
  verify(pkg: string, signal?: AbortSignal) { return this.json<VerifyDto>(`${base}/packages/${id(pkg)}/verify`, signal); }
  cancelVerify(pkg: string, signal?: AbortSignal) { return this.json<VerifyDto>(`${base}/packages/${id(pkg)}/verify`, signal, 'DELETE'); }
}
