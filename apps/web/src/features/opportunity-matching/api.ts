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

/** Splits free text into at most MAX_INTERESTS trimmed, de-duplicated keywords. */
export function parseKeywords(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of text.split(',')) {
    const word = raw.trim().slice(0, MAX_KEYWORD_LENGTH);
    const key = word.toLocaleLowerCase('ko-KR');
    if (!word || seen.has(key)) continue;
    seen.add(key);
    out.push(word);
    if (out.length === MAX_INTERESTS) break;
  }
  return out;
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
