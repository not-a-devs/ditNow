export type Kind = 'all' | 'guide' | 'facility';
export interface GuideSource {
  kind: 'official_summary';
  snapshot_version: string;
  evidence: { url: string; site: 'university' | 'cs'; checked_at: string; existence: 'VERIFIED'; processing_rules: 'PARTIAL'; freshness: 'UNKNOWN'; evidence: string; checked_scope: string };
}
export interface FacilitySource { kind: 'unverified_facility'; verification: 'UNKNOWN'; source_path: 'chatbot/data/facilities.json'; notice: string }
export interface Item { id: string; kind: 'guide' | 'facility'; title: string; summary: string; detail_path: string; source: GuideSource | FacilitySource }
export interface Page { query: string; kind: Kind; items: Item[]; total: number; counts: { guide: number; facility: number }; offset: number; limit: number; complete: boolean; personal_data_access: false; generated: false; notice: string }
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown, max: number, empty = false): v is string => typeof v === 'string' && v.length <= max && (empty || !!v.trim());
const integer = (v: unknown, max: number): v is number => Number.isInteger(v) && Number(v) >= 0 && Number(v) <= max;

function detailPath(path: unknown, kind: string, id: string): path is string {
  if (!text(path, 3000) || path.includes('\\') || path.includes('#')) return false;
  try {
    const url = new URL(path, 'https://ditnow.invalid');
    if (url.origin !== 'https://ditnow.invalid') return false;
    const expected = kind === 'guide' ? '/app/information' : '/app/ai';
    const key = kind === 'guide' ? 'guide' : 'q';
    return path.startsWith(`${expected}?`) && url.pathname === expected
      && [...url.searchParams.keys()].length === 1 && url.searchParams.has(key)
      && (kind === 'guide' ? url.searchParams.get(key) === id.slice(6) : text(url.searchParams.get(key), 500));
  } catch { return false; }
}

function source(value: unknown, kind: string): value is GuideSource | FacilitySource {
  if (!record(value)) return false;
  if (kind === 'facility') return value.kind === 'unverified_facility' && value.verification === 'UNKNOWN'
    && value.source_path === 'chatbot/data/facilities.json' && text(value.notice, 1000);
  if (value.kind !== 'official_summary' || !text(value.snapshot_version, 100)
    || !/^public-campus-\d{4}-\d{2}-\d{2}-v\d+$/.test(value.snapshot_version) || !record(value.evidence)) return false;
  const evidence = value.evidence;
  if (!text(evidence.url, 2048) || /\s|[^\x20-\x7e]/.test(evidence.url)) return false;
  try {
    const url = new URL(evidence.url);
    if (url.protocol !== 'https:' || url.host !== 'www.dit.ac.kr' || url.username || url.password || url.hash
      || !['/kr/', '/kr/index.php', '/cs/', '/cs/index.php'].includes(url.pathname)
      || [...url.searchParams.keys()].some(key => key !== 'pCode')
      || !['university', 'cs'].includes(String(evidence.site))
      || !url.pathname.startsWith(evidence.site === 'cs' ? '/cs/' : '/kr/')) return false;
  } catch { return false; }
  return evidence.existence === 'VERIFIED' && evidence.processing_rules === 'PARTIAL' && evidence.freshness === 'UNKNOWN'
    && text(evidence.checked_at, 10) && /^\d{4}-\d{2}-\d{2}$/.test(evidence.checked_at)
    && Number.isFinite(Date.parse(evidence.checked_at)) && text(evidence.evidence, 600) && text(evidence.checked_scope, 1000);
}

function isItem(v: unknown): v is Item {
  if (!record(v) || !['guide', 'facility'].includes(String(v.kind)) || !text(v.id, 100)
    || !text(v.title, 160) || !text(v.summary, 700, true)) return false;
  const kind = String(v.kind);
  if (kind === 'guide' ? !/^guide:[a-z0-9]+(?:-[a-z0-9]+)*$/.test(v.id) : !/^facility:[A-Za-z0-9_-]{1,80}$/.test(v.id)) return false;
  return detailPath(v.detail_path, kind, v.id) && source(v.source, kind);
}

export function isPage(v: unknown): v is Page {
  if (!record(v) || !text(v.query, 200) || !['all', 'guide', 'facility'].includes(String(v.kind))
    || !Array.isArray(v.items) || v.items.length > 20 || !v.items.every(isItem)
    || !integer(v.total, 200) || !integer(v.offset, 200) || !integer(v.limit, 20) || v.limit < 1
    || !record(v.counts) || !integer(v.counts.guide, 100) || !integer(v.counts.facility, 100)
    || typeof v.complete !== 'boolean' || v.personal_data_access !== false || v.generated !== false || !text(v.notice, 1000)) return false;
  return v.counts.guide + v.counts.facility === v.total && v.items.length <= v.limit
    && v.items.length === Math.max(0, Math.min(v.limit, v.total - v.offset))
    && new Set(v.items.map(item => item.id)).size === v.items.length
    && v.items.every(item => v.kind === 'all' || item.kind === v.kind);
}
