import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../lib/api', async importOriginal => ({ ...(await importOriginal<typeof import('../../lib/api')>()), requestData: vi.fn() }));

import { requestData } from '../../lib/api';
import { advance, create, isItem, isPage, list, remove, type Item } from './api';

const ID = '3f1c2b4a-5d6e-4f70-8a9b-0c1d2e3f4a5b';
const item = (patch: Record<string, unknown> = {}) => ({ id: ID, kind: 'TUITION', scenario: 'STANDARD', status: 'REQUESTED', status_label: '가상 접수', revision: 1,
  created_at: '2026-10-30T01:00:00Z', updated_at: '2026-10-30T10:00:00+09:00', title: '가상 등록금 예시', outcome_text: null, document_text: null,
  source_kind: 'DEMO', persistence: 'PROCESS_MEMORY', official_effect: false, sensitive_content_collected: false, ...patch }) as Item;
const page = (items: unknown[]) => ({ source_kind: 'DEMO', persistence: 'PROCESS_MEMORY', official_effect: false, items });
const mocked = vi.mocked(requestData);
beforeEach(() => { mocked.mockReset(); });

describe('demo service DTO guards', () => {
  it('accepts the exact fictional item and page', () => {
    expect(isItem(item())).toBe(true);
    expect(isItem(item({ kind: 'CERTIFICATE', status: 'COMPLETED', revision: 3, outcome_text: '가상 처리 완료', document_text: '가상 증명 예시' }))).toBe(true);
    expect(isPage(page([item()]))).toBe(true);
  });
  it.each([
    ['extra identity', { owner_id: 'u1' }], ['extra name', { name: '홍길동' }], ['extra amount', { amount: 1000 }],
    ['real source', { source_kind: 'OFFICIAL' }], ['db persistence', { persistence: 'MARIADB' }], ['official effect', { official_effect: true }],
    ['sensitive collected', { sensitive_content_collected: true }], ['naive created', { created_at: '2026-10-30T01:00:00' }],
    ['naive updated', { updated_at: '2026-10-30 01:00' }], ['revision 0', { revision: 0 }], ['revision overflow', { revision: 2147483648 }],
    ['fraction revision', { revision: 1.5 }], ['non-v4 id', { id: '3f1c2b4a-5d6e-1f70-8a9b-0c1d2e3f4a5b' }], ['unknown kind', { kind: 'GRADES' }],
    ['unknown status', { status: 'CANCELLED' }], ['document on non-certificate', { document_text: '문서' }],
    ['document before completion', { kind: 'CERTIFICATE', document_text: '문서' }],
    ['wrong status revision', { status: 'COMPLETED', revision: 1, outcome_text: '가상 처리 완료' }],
    ['completed without outcome', { status: 'COMPLETED', revision: 3 }],
    ['premature outcome', { outcome_text: '가상 처리 완료' }],
    ['certificate without document', { kind: 'CERTIFICATE', status: 'COMPLETED', revision: 3, outcome_text: '가상 처리 완료' }],
  ])('rejects %s', (_, patch) => { expect(isItem(item(patch))).toBe(false); });
  it('rejects missing fields, page extras, duplicates and over-limit pages', () => {
    const missing: Record<string, unknown> = { ...item() }; delete missing.outcome_text;
    expect(isItem(missing)).toBe(false);
    expect(isPage({ ...page([]), owner: 'u1' })).toBe(false);
    expect(isPage({ ...page([]), official_effect: true })).toBe(false);
    expect(isPage(page([item(), item()]))).toBe(false);
    const many = Array.from({ length: 21 }, (_, index) => item({ id: `3f1c2b4a-5d6e-4f70-8a9b-${String(index).padStart(12, '0')}` }));
    expect(isPage(page(many))).toBe(false);
    expect(isPage(page(many.slice(0, 20)))).toBe(true);
  });
});

describe('demo service endpoints', () => {
  it('lists with no-store and signal, rejecting malformed data', async () => {
    const signal = new AbortController().signal;
    mocked.mockResolvedValueOnce(page([item()]));
    expect((await list(signal)).items).toHaveLength(1);
    expect(mocked).toHaveBeenCalledWith('/me/demo-services', { signal, cache: 'no-store' });
    mocked.mockResolvedValueOnce({ ...page([]), persistence: 'MARIADB' });
    await expect(list()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('creates with Idempotency-Key, fixed body and matching echo', async () => {
    mocked.mockResolvedValueOnce(item());
    await create({ kind: 'TUITION', scenario: 'STANDARD', consent: true }, 'key_0123456789abcdef');
    const [path, init] = mocked.mock.calls[0];
    expect(path).toBe('/me/demo-services');
    expect(init).toMatchObject({ method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'key_0123456789abcdef' } });
    expect(JSON.parse(String(init?.body))).toEqual({ kind: 'TUITION', scenario: 'STANDARD', consent: true });
    mocked.mockResolvedValueOnce(item({ kind: 'CERTIFICATE' }));
    await expect(create({ kind: 'TUITION', scenario: 'STANDARD', consent: true }, 'key_0123456789abcdef')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('advances by revision on the item path and refuses unsafe ids before sending', async () => {
    mocked.mockResolvedValueOnce(item({ status: 'IN_PROGRESS', revision: 2 }));
    await advance(item(), 'adv_0123456789abcdef');
    expect(mocked.mock.calls[0][0]).toBe(`/me/demo-services/${ID}/advance`);
    expect(mocked.mock.calls[0][1]).toMatchObject({ method: 'POST', cache: 'no-store', headers: { 'Idempotency-Key': 'adv_0123456789abcdef' } });
    expect(JSON.parse(String(mocked.mock.calls[0][1]?.body))).toEqual({ revision: 1 });
    await expect(advance(item({ id: '../admin' }), 'adv_0123456789abcdef')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    expect(mocked).toHaveBeenCalledTimes(1);
    mocked.mockResolvedValueOnce(item());
    await expect(advance(item(), 'adv_0123456789abcdef')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    mocked.mockResolvedValueOnce(item({ status: 'COMPLETED', revision: 3, outcome_text: '가상 처리 완료' }));
    await expect(advance(item(), 'adv_0123456789abcdef')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
  it('deletes by revision and accepts only the exact synthetic receipt', async () => {
    mocked.mockResolvedValueOnce({ id: ID, deleted: true });
    await expect(remove({ id: ID, revision: 2 })).resolves.toBeUndefined();
    expect(mocked).toHaveBeenCalledWith(`/me/demo-services/${ID}?revision=2`, { method: 'DELETE', signal: undefined, cache: 'no-store' });
    for (const receipt of [{ id: ID, deleted: true, owner: 'u1' }, { id: ID, deleted: false }, { id: '3f1c2b4a-5d6e-4f70-8a9b-000000000000', deleted: true }, null]) {
      mocked.mockResolvedValueOnce(receipt);
      await expect(remove({ id: ID, revision: 2 })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    }
  });
});
