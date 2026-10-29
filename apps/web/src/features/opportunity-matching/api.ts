// FR-OPP-002 client. Paths are relative to the shared requestData base (default /api/v1).
// Responses are personal, so the browser cache is bypassed; the server also sends no-store.
import { requestData } from '../../lib/api';
import type { Interests, MatchFilter, MatchPage, OpportunityBrief } from './types';

const PATH = '/me/opportunity-matches';
export const MAX_INTERESTS = 5;
export const MAX_KEYWORD_LENGTH = 20;

function appendInterests(params: URLSearchParams, interests: Interests): void {
  for (const kind of interests.kinds) params.append('interest_kind', kind);
  for (const keyword of interests.keywords) params.append('interest_keyword', keyword);
}

function withQuery(path: string, params: URLSearchParams): string {
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

// Mirrors the server's str.isprintable(): control, format (e.g. ZWJ), surrogate, private-use,
// unassigned, line/paragraph separators and every space separator except ASCII space (e.g. NBSP).
const NOT_PRINTABLE = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}]|(?! )\p{Zs}/u;

export type ParsedKeywords = { ok: true; keywords: string[] } | { ok: false; message: string };

/**
 * Splits free text on commas into trimmed, de-duplicated keywords. Nothing is silently cut:
 * a keyword over MAX_KEYWORD_LENGTH code points (the server's unit, so an emoji counts as one),
 * a non-printable character or more than MAX_INTERESTS keywords is rejected with a message.
 */
export function parseKeywords(text: string): ParsedKeywords {
  const seen = new Set<string>();
  const keywords: string[] = [];
  for (const raw of text.split(',')) {
    const word = raw.trim();
    if (!word) continue;
    if (Array.from(word).length > MAX_KEYWORD_LENGTH)
      return { ok: false, message: `키워드는 각각 ${MAX_KEYWORD_LENGTH}자 이하로 입력하세요.` };
    if (NOT_PRINTABLE.test(word))
      return { ok: false, message: '키워드에 보이지 않는 문자나 특수 공백·결합 문자는 쓸 수 없습니다.' };
    const key = word.toLocaleLowerCase('ko-KR');
    if (seen.has(key)) continue;
    seen.add(key);
    keywords.push(word);
  }
  if (keywords.length > MAX_INTERESTS)
    return { ok: false, message: `관심 키워드는 최대 ${MAX_INTERESTS}개까지 입력할 수 있습니다.` };
  return { ok: true, keywords };
}

export function listMatches(filter: MatchFilter, signal?: AbortSignal): Promise<MatchPage> {
  const params = new URLSearchParams();
  appendInterests(params, filter);
  if (filter.kind) params.set('kind', filter.kind);
  if (filter.includeClosed) params.set('include_closed', 'true');
  if (filter.limit) params.set('limit', String(filter.limit));
  if (filter.cursor) params.set('cursor', filter.cursor);
  return requestData<MatchPage>(withQuery(PATH, params), { cache: 'no-store', signal });
}

export function getBrief(
  opportunityId: string,
  interests: Interests,
  signal?: AbortSignal,
): Promise<OpportunityBrief> {
  const params = new URLSearchParams();
  appendInterests(params, interests);
  const path = `${PATH}/${encodeURIComponent(opportunityId)}/brief`;
  return requestData<OpportunityBrief>(withQuery(path, params), { cache: 'no-store', signal });
}

/** Defense in depth: only absolute http(s) links without credentials become anchors. */
export function safeHref(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}
