export type Category = 'university' | 'campus' | 'disclosure' | 'news' | 'department';
export type Site = 'university' | 'cs';
export const categories: Record<Category, string> = { university: '대학 소개', campus: '캠퍼스', disclosure: '정보 공개', news: '대학 소식', department: '학과 안내' };
export const sites: Record<Site, string> = { university: '대학 홈페이지', cs: '컴퓨터소프트웨어과' };
export interface Source { url: string; site: Site; checked_at: string; existence: 'VERIFIED'; processing_rules: 'PARTIAL'; freshness: 'UNKNOWN'; evidence: string; checked_scope: string; }
export interface Card { id: string; title: string; category: Category; summary: string; tags: string[]; source: Source; }
export interface Guide extends Card { sections: { heading: string; paragraphs: string[] }[]; feature_ids: string[]; content_kind: 'EDITORIAL_PUBLIC_SUMMARY'; }
export interface GuidePage { items: Card[]; total: number; offset: number; limit: number; snapshot_version: string; notice: string; }

const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown, max: number): value is string => typeof value === 'string' && !!value.trim() && value.length <= max;
const strings = (value: unknown, count: number, max: number): value is string[] => Array.isArray(value) && value.length <= count && value.every(item => text(item, max));
export function officialUrl(value: unknown): value is string {
  if (typeof value !== 'string' || /\s|[^\x20-\x7e]/.test(value)) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.host === 'www.dit.ac.kr' && !url.username && !url.password && !url.hash
      && ['/kr/', '/kr/index.php', '/cs/', '/cs/index.php'].includes(url.pathname)
      && [...url.searchParams.keys()].every(key => key === 'pCode');
  } catch { return false; }
}
function isSource(value: unknown): value is Source {
  return record(value) && officialUrl(value.url) && ['university', 'cs'].includes(String(value.site))
    && new URL(value.url).pathname.startsWith(value.site === 'cs' ? '/cs/' : '/kr/')
    && text(value.checked_at, 10) && /^\d{4}-\d{2}-\d{2}$/.test(value.checked_at)
    && Number.isFinite(Date.parse(value.checked_at)) && value.existence === 'VERIFIED'
    && value.processing_rules === 'PARTIAL' && value.freshness === 'UNKNOWN'
    && text(value.evidence, 600) && text(value.checked_scope, 1000);
}
export function isCard(value: unknown): value is Card {
  return record(value) && text(value.id, 80) && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value.id)
    && text(value.title, 160) && Object.hasOwn(categories, String(value.category)) && text(value.summary, 700)
    && strings(value.tags, 12, 50) && isSource(value.source);
}
export function isGuidePage(value: unknown): value is GuidePage {
  return record(value) && Array.isArray(value.items) && value.items.length <= 50 && value.items.every(isCard)
    && Number.isInteger(value.total) && Number(value.total) >= value.items.length && Number(value.total) <= 100
    && Number.isInteger(value.offset) && Number(value.offset) >= 0
    && Number.isInteger(value.limit) && Number(value.limit) >= 1 && Number(value.limit) <= 50
    && text(value.snapshot_version, 100) && /^public-campus-\d{4}-\d{2}-\d{2}-v\d+$/.test(value.snapshot_version)
    && text(value.notice, 1000);
}
export function isGuide(value: unknown): value is Guide {
  if (!isCard(value) || !record(value)) return false;
  return value.content_kind === 'EDITORIAL_PUBLIC_SUMMARY' && strings(value.feature_ids, 6, 30)
    && Array.isArray(value.sections) && value.sections.length > 0 && value.sections.length <= 8
    && value.sections.every(section => record(section) && text(section.heading, 120) && strings(section.paragraphs, 6, 1200) && section.paragraphs.length > 0);
}
