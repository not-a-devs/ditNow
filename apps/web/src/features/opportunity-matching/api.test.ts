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

  it('parses keywords: trims, skips empties and dedupes case-insensitively', () => {
    expect(parseKeywords(' AI, ai ,  ,데이터,x,y')).toEqual({ ok: true, keywords: ['AI', '데이터', 'x', 'y'] });
    expect(parseKeywords('')).toEqual({ ok: true, keywords: [] });
  });

  it('counts code points like the server and accepts exactly 20', () => {
    for (const word of ['a'.repeat(20), '가'.repeat(20), '😀'.repeat(20), 'a' + '😀'.repeat(19)]) {
      expect(parseKeywords(word)).toEqual({ ok: true, keywords: [word] });
    }
  });

  it.each([
    ['21 ASCII letters', 'a'.repeat(21), '20자 이하'],
    ['21 emoji (42 UTF-16 units)', '😀'.repeat(21), '20자 이하'],
    ['30 letters are not cut to 20', 'a'.repeat(30), '20자 이하'],
    ['no-break space', '장학 금', '보이지 않는 문자'],
    ['zero-width joiner emoji', '👩‍💻', '보이지 않는 문자'],
    ['lone surrogate', 'a\ud83d', '보이지 않는 문자'],
    ['tab', '탭\t문자', '보이지 않는 문자'],
    ['six distinct keywords', 'a,b,c,d,e,f', '최대 5개'],
  ])('rejects %s instead of silently changing it', (_name, text, message) => {
    const parsed = parseKeywords(text);
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) expect(parsed.message).toContain(message);
  });

  it('sends emoji keywords intact without replacement characters', async () => {
    const fetch = stubFetch();
    const word = 'a' + '😀'.repeat(10);
    const parsed = parseKeywords(word);
    expect(parsed).toEqual({ ok: true, keywords: [word] });
    await listMatches({ kinds: [], keywords: parsed.ok ? parsed.keywords : [] });
    const url = new URL(fetch.mock.calls[0][0]);
    expect(url.searchParams.get('interest_keyword')).toBe(word);
    expect(url.search).not.toContain('%EF%BF%BD');
  });

  it('allows only absolute http(s) links without credentials', () => {
    expect(safeHref('https://example.test/a')).toBe('https://example.test/a');
    expect(safeHref('http://example.test/')).toBe('http://example.test/');
    for (const bad of ['javascript:alert(1)', 'data:text/html,x', '/relative', 'https://u:p@example.test/', '', null]) {
      expect(safeHref(bad)).toBeNull();
    }
  });
});
