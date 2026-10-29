// Uses the real shared requestData with only fetch stubbed, so the URL asserted is exactly what
// the browser would request. Guards against the /api/v1/api/v1 double prefix and checks that
// runtime guards reject shapes/claims the server must never send.
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../lib/api';
import * as api from './api';
import * as guard from './guards';
import type { EmployerDraft, ProgramApplication } from './types';

const ID = '00000000-0000-4000-8000-000000000001';
const DRAFT = { id: ID, revision: 4 } as EmployerDraft;
const APPLICATION = { id: ID, revision: 2 } as ProgramApplication;

function stubFetch(data: unknown = {}) {
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ data }), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

const calls: Array<[string, () => Promise<unknown>, string, string]> = [
  ['jobs', () => api.listJobs({ q: ' 인턴 ', department: 'CSE', openOnly: true }), 'GET', '/api/v1/careers/jobs?q=%EC%9D%B8%ED%84%B4&department=CSE&open_only=true'],
  ['contests', () => api.listContests(), 'GET', '/api/v1/careers/contests'],
  ['profile', () => api.getProfile(), 'GET', '/api/v1/careers/me/profile'],
  ['create profile', () => api.createProfile({ alias: '별빛', desired_roles: [], skills: [], summary: '' }, 'profile-key-1'), 'POST', '/api/v1/careers/me/profile'],
  ['update profile', () => api.updateProfile(3, { summary: 'x' }), 'PATCH', '/api/v1/careers/me/profile'],
  ['delete profile', () => api.deleteProfile(3), 'DELETE', '/api/v1/careers/me/profile'],
  ['programs', () => api.listPrograms(), 'GET', '/api/v1/careers/programs'],
  ['apply', () => api.applyToProgram(ID, '', 'apply-key-1'), 'POST', `/api/v1/careers/programs/${ID}/applications`],
  ['applications', () => api.listApplications(), 'GET', '/api/v1/careers/me/program-applications'],
  ['cancel', () => api.cancelApplication(APPLICATION), 'POST', `/api/v1/careers/me/program-applications/${ID}/cancel`],
  ['drafts', () => api.listEmployerDrafts(), 'GET', '/api/v1/careers/employer-requests'],
  ['create draft', () => api.createEmployerDraft({ company_alias: 'a', role_title: 'b', description: 'c', employment_type: 'internship', closes_at: '2026-11-30T23:59:00+09:00' }, 'draft-key-1'), 'POST', '/api/v1/careers/employer-requests'],
  ['update draft', () => api.updateEmployerDraft(DRAFT, { role_title: 'x' }), 'PATCH', `/api/v1/careers/employer-requests/${ID}`],
  ['delete draft', () => api.deleteEmployerDraft(DRAFT), 'DELETE', `/api/v1/careers/employer-requests/${ID}`],
];

describe('careers API client through the shared transport', () => {
  it.each(calls)('%s hits the default base exactly once', async (_name, call, method, path) => {
    const fetch = stubFetch();
    await call().catch(() => undefined); // empty data fails the guard; only the URL matters here
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe(`${window.location.origin}${path}`);
    expect(new URL(url).pathname).not.toContain('/api/v1/api/v1');
    expect(init.method ?? 'GET').toBe(method);
  });

  it('respects a configured absolute API base without doubling the prefix', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test/api/v1');
    const fetch = stubFetch({ profile: null });
    await api.getProfile();
    expect(fetch.mock.calls[0][0]).toBe('https://api.example.test/api/v1/careers/me/profile');
  });

  it('sends If-Match revisions and the caller key unchanged', async () => {
    const fetch = stubFetch();
    await api.deleteEmployerDraft(DRAFT).catch(() => undefined);
    await api.applyToProgram(ID, '메모', 'apply-same-key').catch(() => undefined);
    expect(fetch.mock.calls[0][1].headers['If-Match']).toBe('4');
    expect(fetch.mock.calls[1][1].headers['Idempotency-Key']).toBe('apply-same-key');
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ note: '메모' });
  });

  it('maps server errors to ApiError with code, status and request id', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ code: 'FORBIDDEN', message: 'x', request_id: '12345678-1234-1234-1234-123456789012' }), { status: 403 })));
    await expect(api.listEmployerDrafts()).rejects.toMatchObject({ code: 'FORBIDDEN', status: 403, requestId: '12345678-1234-1234-1234-123456789012' });
  });
});

describe('IntentKey', () => {
  it('reuses the key for the same input and rotates it when the input changes', () => {
    const intent = new api.IntentKey('apply');
    const first = intent.keyFor({ note: 'a' });
    expect(intent.keyFor({ note: 'a' })).toBe(first);
    const changed = intent.keyFor({ note: 'b' });
    expect(changed).not.toBe(first);
    intent.settle();
    expect(intent.keyFor({ note: 'b' })).not.toBe(changed);
    expect(first).toMatch(/^apply-[A-Za-z0-9-]{8,96}$/);
  });
});

describe('runtime guards', () => {
  const draft = {
    id: ID, company_alias: '가상테크', role_title: '인턴', description: 'x', employment_type: 'internship',
    closes_at: '2026-11-30T14:59:00Z', revision: 1, created_at: '2026-10-30T03:00:00Z', updated_at: '2026-10-30T03:00:00Z',
    status: 'draft', publishable: false,
  };

  it('accepts a valid draft and rejects publication or review claims', () => {
    expect(guard.employerDraft(draft).status).toBe('draft');
    expect(() => guard.employerDraft({ ...draft, publishable: true })).toThrow(ApiError);
    expect(() => guard.employerDraft({ ...draft, status: 'published' })).toThrow(ApiError);
    expect(() => guard.employerDraft({ ...draft, closes_at: '2026-11-30T14:59:00' })).toThrow(ApiError); // naive
  });

  it('downgrades an official label without link/date and drops non-https links', () => {
    const job = {
      id: ID, title: 't', organization: 'o', department_codes: [], apply_starts_at: null, deadline_at: null,
      deadline_passed: false, provenance: 'OFFICIAL_PUBLIC', original_url: 'javascript:alert(1)', checked_at: '2026-10-29T00:00:00Z',
      platform_receives_application: false,
    };
    const parsed = guard.jobSummary(job);
    expect(parsed.provenance).toBe('UNKNOWN');
    expect(parsed.original_url).toBeNull();
    expect(() => guard.jobSummary({ ...job, platform_receives_application: true })).toThrow(ApiError);
    expect(guard.safeHref('http://job.dit.ac.kr/')).toBeNull();
    expect(guard.safeHref('https://job.dit.ac.kr/page/main/')).toBe('https://job.dit.ac.kr/page/main/');
  });

  it('rejects a profile that claims to be shared', () => {
    const profile = { id: ID, alias: '별빛', desired_roles: [], skills: [], summary: '', revision: 1, created_at: '2026-10-30T03:00:00Z', updated_at: '2026-10-30T03:00:00Z', shared_with: [], is_virtual: true };
    expect(guard.profile(profile).alias).toBe('별빛');
    expect(() => guard.profile({ ...profile, shared_with: ['employer'] })).toThrow(ApiError);
    expect(() => guard.profile({ ...profile, is_virtual: false })).toThrow(ApiError);
  });
});
