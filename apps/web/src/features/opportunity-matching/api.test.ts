// FR-OPP-002 client contract through the real shared transport (fetch stubbed).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getBrief, listMatches, parseKeywords, safeHref } from './api';

function stubFetch() {
  const fetch = vi.fn((_url: string, _init: RequestInit = {}) =>
    Promise.resolve(new Response(JSON.stringify({ data: { items: [] } }), { status: 200 })),
  );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

afterEach(() => vi.unstubAllGlobals());

describe('opportunity matching api', () => {
  it('builds the list URL with repeated interests once under /api/v1 and bypasses cache', async () => {
    const fetch = stubFetch();
    await listMatches({
      kinds: ['contest', 'scholarship'],
      keywords: ['AI', '데이터 분석'],
      kind: 'contest',
      includeClosed: true,
      limit: 10,
      cursor: '10.0123456789abcdef',
    });
    const [url, init] = fetch.mock.calls[0];
    const parsed = new URL(url);
    expect(parsed.pathname).toBe('/api/v1/me/opportunity-matches');
    expect(parsed.searchParams.getAll('interest_kind')).toEqual(['contest', 'scholarship']);
    expect(parsed.searchParams.getAll('interest_keyword')).toEqual(['AI', '데이터 분석']);
    expect(parsed.searchParams.get('kind')).toBe('contest');
    expect(parsed.searchParams.get('include_closed')).toBe('true');
    expect(parsed.searchParams.get('cursor')).toBe('10.0123456789abcdef');
    expect(init?.cache).toBe('no-store');
    expect(parsed.searchParams.has('user_id')).toBe(false);
  });

  it('omits empty filters', async () => {
    const fetch = stubFetch();
    await listMatches({ kinds: [], keywords: [] });
    expect(new URL(fetch.mock.calls[0][0]).search).toBe('');
  });

  it('encodes the opportunity id in the brief path and never sends path traversal', async () => {
    const fetch = stubFetch();
    await getBrief('a?c#d', { kinds: ['event'], keywords: [] });
    const parsed = new URL(fetch.mock.calls[0][0]);
    expect(parsed.pathname).toBe('/api/v1/me/opportunity-matches/a%3Fc%23d/brief');
    expect(parsed.searchParams.getAll('interest_kind')).toEqual(['event']);
    // The shared client rejects encoded separators, so a crafted id cannot escape the path.
    await expect(getBrief('../x/y', { kinds: [], keywords: [] })).rejects.toMatchObject({ code: 'CONFIGURATION' });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('parses keywords: trims, dedupes case-insensitively, caps count and length', () => {
    expect(parseKeywords(' AI, ai ,  ,데이터,x,y,z,w')).toEqual(['AI', '데이터', 'x', 'y', 'z']);
    expect(parseKeywords('a'.repeat(30))).toEqual(['a'.repeat(20)]);
    expect(parseKeywords('')).toEqual([]);
  });

  it('allows only absolute http(s) links without credentials', () => {
    expect(safeHref('https://example.test/a')).toBe('https://example.test/a');
    expect(safeHref('http://example.test/')).toBe('http://example.test/');
    for (const bad of ['javascript:alert(1)', 'data:text/html,x', '/relative', 'https://u:p@example.test/', '', null]) {
      expect(safeHref(bad)).toBeNull();
    }
  });
});
