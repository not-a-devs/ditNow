// API-JOB client over the shared requestData<T> (src/lib/api.ts), which already prefixes the
// configured base (default /api/v1) and returns success.data only. Paths here are relative to
// that base — never add /api/v1 again (regression-tested in api.test.ts).
import { requestData } from '../../lib/api';
import * as guard from './guards';
import type {
  CareerProfile,
  ContestPage,
  Deleted,
  EmployerDraft,
  EmployerDraftInput,
  JobFilter,
  JobPage,
  ProfileInput,
  ProgramApplication,
  ProgramList,
} from './types';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

function withKey(key: string): Record<string, string> {
  return { ...JSON_HEADERS, 'Idempotency-Key': key };
}

function ifMatch(revision: number): Record<string, string> {
  return { ...JSON_HEADERS, 'If-Match': String(revision) };
}

const seg = encodeURIComponent;

export async function listJobs(filter: JobFilter = {}): Promise<JobPage> {
  const params = new URLSearchParams();
  if (filter.q?.trim()) params.set('q', filter.q.trim());
  if (filter.department?.trim()) params.set('department', filter.department.trim());
  if (filter.openOnly) params.set('open_only', 'true');
  if (filter.cursor) params.set('cursor', filter.cursor);
  const query = params.toString();
  return guard.jobPage(await requestData<unknown>(`/careers/jobs${query ? `?${query}` : ''}`));
}

export async function listContests(cursor?: string | null): Promise<ContestPage> {
  const query = cursor ? `?${new URLSearchParams({ cursor })}` : '';
  return guard.contestPage(await requestData<unknown>(`/careers/contests${query}`));
}

export async function getProfile(): Promise<CareerProfile | null> {
  return guard.profileEnvelope(await requestData<unknown>('/careers/me/profile'));
}

export async function createProfile(input: ProfileInput, key: string): Promise<CareerProfile> {
  return guard.profile(
    await requestData<unknown>('/careers/me/profile', { method: 'POST', headers: withKey(key), body: JSON.stringify(input) }),
  );
}

export async function updateProfile(revision: number, input: Partial<ProfileInput>): Promise<CareerProfile> {
  return guard.profile(
    await requestData<unknown>('/careers/me/profile', { method: 'PATCH', headers: ifMatch(revision), body: JSON.stringify(input) }),
  );
}

export async function deleteProfile(revision: number): Promise<Deleted> {
  return guard.deleted(await requestData<unknown>('/careers/me/profile', { method: 'DELETE', headers: ifMatch(revision) }));
}

export async function listPrograms(): Promise<ProgramList> {
  return guard.programList(await requestData<unknown>('/careers/programs'));
}

export async function applyToProgram(programId: string, note: string, key: string): Promise<ProgramApplication> {
  return guard.application(
    await requestData<unknown>(`/careers/programs/${seg(programId)}/applications`, {
      method: 'POST',
      headers: withKey(key),
      body: JSON.stringify({ note }),
    }),
  );
}

export async function listApplications(): Promise<ProgramApplication[]> {
  return guard.applicationList(await requestData<unknown>('/careers/me/program-applications'));
}

export async function cancelApplication(application: ProgramApplication): Promise<ProgramApplication> {
  return guard.application(
    await requestData<unknown>(`/careers/me/program-applications/${seg(application.id)}/cancel`, {
      method: 'POST',
      headers: ifMatch(application.revision),
    }),
  );
}

export async function listEmployerDrafts(): Promise<EmployerDraft[]> {
  return guard.employerDraftList(await requestData<unknown>('/careers/employer-requests'));
}

export async function createEmployerDraft(input: EmployerDraftInput, key: string): Promise<EmployerDraft> {
  return guard.employerDraft(
    await requestData<unknown>('/careers/employer-requests', { method: 'POST', headers: withKey(key), body: JSON.stringify(input) }),
  );
}

export async function updateEmployerDraft(draft: EmployerDraft, patch: Partial<EmployerDraftInput>): Promise<EmployerDraft> {
  return guard.employerDraft(
    await requestData<unknown>(`/careers/employer-requests/${seg(draft.id)}`, {
      method: 'PATCH',
      headers: ifMatch(draft.revision),
      body: JSON.stringify(patch),
    }),
  );
}

export async function deleteEmployerDraft(draft: EmployerDraft): Promise<Deleted> {
  return guard.deleted(
    await requestData<unknown>(`/careers/employer-requests/${seg(draft.id)}`, { method: 'DELETE', headers: ifMatch(draft.revision) }),
  );
}

/**
 * One key per user intent. Retrying the *same* input reuses the key so the server replays
 * instead of duplicating; any change to the input rotates it. `settle()` after success.
 */
export class IntentKey {
  private current: { fingerprint: string; key: string } | null = null;

  constructor(private readonly prefix: string) {}

  keyFor(input: unknown): string {
    const fingerprint = JSON.stringify(input);
    if (this.current?.fingerprint !== fingerprint) {
      this.current = { fingerprint, key: `${this.prefix}-${crypto.randomUUID()}` };
    }
    return this.current.key;
  }

  settle(): void {
    this.current = null;
  }
}
