import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, requestData } from '../../lib/api';
import { ambiguous, isItem, isPage, listQueue, patchItem, readItem, type Item } from './api';

vi.mock('../../lib/api', async original => ({ ...await original<typeof import('../../lib/api')>(), requestData: vi.fn() }));
const mocked = vi.mocked(requestData);
const A = '11111111-1111-4111-8111-111111111111';
const meta = { source_kind: 'DEMO', storage: 'PROCESS_MEMORY', official_effect: false, restart_reset: true } as const;
const item = (over: Partial<Item> = {}): Item => ({ id: A, category: 'REPORT', demo_label: 'DEMO_ITEM_01', status: 'PENDING', classification: null, resolution: null, note_code: null, revision: 1, meta, ...over });
const signal = new AbortController().signal;

beforeEach(() => mocked.mockReset());

describe('admin audit queue api guards', () => {
  it('accepts consistent fixed DEMO items only', () => {
    expect(isItem(item())).toBe(true);
    expect(isItem(item({ status: 'CLASSIFIED', classification: 'NO_ACTION', note_code: 'DEMO_CHECKED', revision: 2 }))).toBe(true);
    expect(isItem({ ...item(), author_id: A })).toBe(false);
    expect(isItem({ ...item(), content: 'x' })).toBe(false);
    expect(isItem(item({ meta: { ...meta, official_effect: true } as never }))).toBe(false);
    expect(isItem(item({ status: 'RESOLVED' }))).toBe(false);
    expect(isItem(item({ status: 'PENDING', classification: 'NO_ACTION' }))).toBe(false);
    expect(isItem(item({ category: 'USER' as never }))).toBe(false);
    expect(isItem(item({ demo_label: '<script>' }))).toBe(false);
    expect(isItem(item({ revision: 1.5 }))).toBe(false);
    // Fixed workflow: PENDING 1 -> CLASSIFIED 2 -> RESOLVED 3 only.
    const resolved = { status: 'RESOLVED', classification: 'NO_ACTION', resolution: 'KEEP_DEMO', note_code: 'DEMO_CHECKED' } as const;
    expect(isItem(item({ ...resolved, revision: 3 }))).toBe(true);
    expect(isItem(item({ ...resolved, revision: 2 }))).toBe(false);
    expect(isItem(item({ ...resolved, revision: 4 }))).toBe(false);
    expect(isItem(item({ status: 'CLASSIFIED', classification: 'NO_ACTION', note_code: 'DEMO_CHECKED', revision: 3 }))).toBe(false);
    expect(isItem(item({ revision: 2 }))).toBe(false);
    expect(isPage({ items: Array.from({ length: 21 }, () => item()), meta })).toBe(false);
    expect(isPage({ items: [item()], meta, extra: 1 })).toBe(false);
  });

  it('uses the feature prefix exactly once and enum query params', async () => {
    mocked.mockResolvedValue({ items: [item()], meta });
    await listQueue({ status: 'PENDING', category: 'REPORT' }, signal);
    await listQueue({ status: '', category: '' }, signal);
    expect(mocked.mock.calls[0][0]).toBe('/admin-audit-queue?status=PENDING&category=REPORT');
    expect(mocked.mock.calls[1][0]).toBe('/admin-audit-queue');
    mocked.mockResolvedValue(item());
    await readItem(A, signal);
    expect(mocked.mock.calls[2][0]).toBe(`/admin-audit-queue/${A}`);
    // safeId rejects synchronously, before any request is built.
    expect(() => readItem('../x', signal)).toThrow(ApiError);
    expect(() => readItem('../x', signal)).toThrow(expect.objectContaining({ code: 'VALIDATION' }));
    expect(mocked).toHaveBeenCalledTimes(3);
  });

  it('sends only enum body with idempotency key and validates the receipt', async () => {
    const receipt = item({ status: 'CLASSIFIED', classification: 'NO_ACTION', note_code: 'DEMO_CHECKED', revision: 2 });
    mocked.mockResolvedValue(receipt);
    await expect(patchItem(A, { revision: 1, classification: 'NO_ACTION', note_code: 'DEMO_CHECKED' }, 'key-1234567890abcdef', signal)).resolves.toEqual(receipt);
    const [path, init] = mocked.mock.calls[0];
    expect(path).toBe(`/admin-audit-queue/${A}`);
    expect(init?.method).toBe('PATCH');
    expect(JSON.parse(init?.body as string)).toEqual({ revision: 1, classification: 'NO_ACTION', note_code: 'DEMO_CHECKED' });
    expect((init?.headers as Record<string, string>)['Idempotency-Key']).toBe('key-1234567890abcdef');
    mocked.mockResolvedValue(item({ status: 'CLASSIFIED', classification: 'NO_ACTION', note_code: 'DEMO_CHECKED', revision: 5 }));
    await expect(patchItem(A, { revision: 1, classification: 'NO_ACTION', note_code: 'DEMO_CHECKED' }, 'key-1234567890abcdef', signal)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });

  it('rejects well-formed receipts that do not match the submitted step', async () => {
    const B = '22222222-2222-4222-8222-222222222222';
    const classified = { status: 'CLASSIFIED', classification: 'NO_ACTION', note_code: 'DEMO_CHECKED', revision: 2 } as const;
    const resolved = { status: 'RESOLVED', classification: 'NO_ACTION', resolution: 'KEEP_DEMO', note_code: 'DEMO_POLICY_REVIEW', revision: 3 } as const;
    const classify = { revision: 1, classification: 'NO_ACTION', note_code: 'DEMO_CHECKED' } as const;
    const resolve = { revision: 2, resolution: 'KEEP_DEMO', note_code: 'DEMO_POLICY_REVIEW' } as const;
    for (const bad of [item({ ...classified, classification: 'REVIEW_NEEDED' }), item({ ...classified, id: B }),
      item({ ...classified, note_code: 'DEMO_POLICY_REVIEW' }), item(), item({ ...resolved, note_code: 'DEMO_CHECKED' })]) {
      mocked.mockResolvedValueOnce(bad);
      await expect(patchItem(A, classify, 'key-1234567890abcdef', signal)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    }
    for (const bad of [item(classified), item({ ...resolved, resolution: 'RESOLVE_DEMO' }), item({ ...resolved, id: B }), item({ ...resolved, note_code: 'DEMO_CHECKED' })]) {
      mocked.mockResolvedValueOnce(bad);
      await expect(patchItem(A, resolve, 'key-1234567890abcdef', signal)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    }
    mocked.mockResolvedValueOnce(item(resolved));
    await expect(patchItem(A, resolve, 'key-1234567890abcdef', signal)).resolves.toMatchObject({ status: 'RESOLVED', revision: 3 });
  });

  it('classifies ambiguous failures', () => {
    expect(ambiguous(new ApiError('NETWORK', 0))).toBe(true);
    expect(ambiguous(new ApiError('UNAVAILABLE', 503))).toBe(true);
    expect(ambiguous(new ApiError('INVALID_RESPONSE', 200))).toBe(true);
    expect(ambiguous(new ApiError('CONFLICT', 409))).toBe(false);
    expect(ambiguous(new ApiError('VALIDATION', 400))).toBe(false);
  });
});
