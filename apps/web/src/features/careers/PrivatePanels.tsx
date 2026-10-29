// Private careers panels. On 401/403 a panel reports to the parent, which unmounts it so the
// personal data in its state is discarded; responses that arrive after unmount are dropped
// (useAlive) and trigger no follow-up request. Forms keep their input after a failure, retries
// of the same input reuse the same Idempotency-Key, and success is only shown for a guarded reply.
import { useCallback, useEffect, useRef, useState, type FormEvent, type MutableRefObject, type ReactNode } from 'react';
import { ApiError } from '../../lib/api';
import * as api from './api';
import type { CareerProfile, EmployerDraft, EmploymentType, Program, ProgramApplication } from './types';
import {
  ErrorBox,
  Loading,
  ProvenanceBadge,
  SourceLink,
  authCode,
  describeError,
  formatDate,
  type Load,
  type PrivateArea,
} from './ui';

export type AuthHandler = (area: PrivateArea, error: unknown) => void;

type Failure = { message: string; requestId?: string; conflict: boolean } | null;

const splitList = (value: string) => value.split(',').map((v) => v.trim()).filter(Boolean);

/** False once the component unmounted, so late replies cannot refill discarded state. */
function useAlive(): MutableRefObject<boolean> {
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  return alive;
}

function useFailure(area: PrivateArea, onAuthError: AuthHandler, alive: MutableRefObject<boolean>) {
  const [failure, setFailure] = useState<Failure>(null);
  const fail = useCallback(
    (error: unknown) => {
      // A late 401/403 still reaches the parent: it can only remove more, never show data.
      if (authCode(error)) onAuthError(area, error);
      else if (alive.current) setFailure({ ...describeError(error), conflict: error instanceof ApiError && error.status === 409 });
    },
    [alive, area, onAuthError],
  );
  return { failure, setFailure, fail };
}

// ------------------------------------------------------------ FR-JOB-002 virtual profile

type ProfileForm = { alias: string; roles: string; skills: string; summary: string };
const EMPTY_PROFILE: ProfileForm = { alias: '', roles: '', skills: '', summary: '' };

function toForm(profile: CareerProfile | null): ProfileForm {
  if (!profile) return EMPTY_PROFILE;
  return { alias: profile.alias, roles: profile.desired_roles.join(', '), skills: profile.skills.join(', '), summary: profile.summary };
}

export function ProfilePanel({ onAuthError }: { onAuthError: AuthHandler }) {
  const [profile, setProfile] = useState<Load<CareerProfile | null>>({ state: 'loading' });
  const [form, setForm] = useState<ProfileForm>(EMPTY_PROFILE);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const alive = useAlive();
  const { failure, setFailure, fail } = useFailure('profile', onAuthError, alive);
  const intent = useRef(new api.IntentKey('profile'));

  const load = useCallback(() => {
    setProfile({ state: 'loading' });
    api.getProfile().then(
      (data) => {
        if (!alive.current) return;
        setProfile({ state: 'ready', data });
        setForm(toForm(data));
      },
      (error) => {
        if (authCode(error)) onAuthError('profile', error);
        else if (alive.current) setProfile({ state: 'error', ...describeError(error) });
      },
    );
  }, [alive, onAuthError]);
  useEffect(load, [load]);

  if (profile.state === 'loading') return <Loading label="내 진로 요약을 불러오는 중…" />;
  if (profile.state === 'error') return <ErrorBox message={profile.message} requestId={profile.requestId} onRetry={load} />;
  const current = profile.data;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const input = { alias: form.alias.trim(), desired_roles: splitList(form.roles), skills: splitList(form.skills), summary: form.summary.trim() };
    setBusy(true);
    setNotice(null);
    setFailure(null);
    const request = current
      ? api.updateProfile(current.revision, input)
      : api.createProfile(input, intent.current.keyFor(input));
    request.then(
      (saved) => {
        if (!alive.current) return;
        intent.current.settle();
        setProfile({ state: 'ready', data: saved });
        setForm(toForm(saved));
        setNotice('저장했습니다. 본인만 볼 수 있는 가상 기록입니다.');
      },
      fail,
    ).finally(() => alive.current && setBusy(false));
  };

  const remove = () => {
    if (!current) return;
    setBusy(true);
    setNotice(null);
    setFailure(null);
    api.deleteProfile(current.revision).then(
      () => {
        if (!alive.current) return;
        setProfile({ state: 'ready', data: null });
        setForm(EMPTY_PROFILE);
        setNotice('삭제했습니다.');
      },
      fail,
    ).finally(() => alive.current && setBusy(false));
  };

  return (
    <section aria-labelledby="careers-profile" className="space-y-3">
      <h2 id="careers-profile" className="text-lg font-semibold">가상 진로·이력 요약</h2>
      <p className="rounded bg-amber-50 p-2 text-xs text-amber-900">
        실명·연락처·이메일·링크·파일은 입력하지 마세요. 가상 별칭과 희망 직무·기술만 저장하며, 상담자·기업과 공유되지 않습니다.
      </p>
      {!current && <p className="text-sm text-slate-500">아직 작성한 진로 요약이 없습니다.</p>}
      <form onSubmit={submit} className="grid gap-2 text-sm">
        <label className="flex flex-col">가상 별칭
          <input required minLength={2} maxLength={30} value={form.alias} onChange={(e) => setForm({ ...form, alias: e.target.value })} className="rounded border px-2 py-1" />
        </label>
        <label className="flex flex-col">희망 직무(쉼표로 구분, 최대 5개)
          <input value={form.roles} onChange={(e) => setForm({ ...form, roles: e.target.value })} className="rounded border px-2 py-1" />
        </label>
        <label className="flex flex-col">기술(쉼표로 구분, 최대 20개)
          <input value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} className="rounded border px-2 py-1" />
        </label>
        <label className="flex flex-col">요약
          <textarea maxLength={500} value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} className="rounded border px-2 py-1" />
        </label>
        <div className="flex gap-2">
          <button type="submit" disabled={busy} className="rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-50">{current ? '수정 저장' : '작성'}</button>
          {current && <button type="button" disabled={busy} onClick={remove} className="rounded border px-3 py-1 disabled:opacity-50">삭제</button>}
        </div>
      </form>
      {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
      {failure && <ErrorBox message={failure.message} requestId={failure.requestId} onRetry={failure.conflict ? load : undefined} />}
    </section>
  );
}

// ------------------------------------------------------------ FR-JOB-003 / FR-OPP-006 programs

function MyApplications({ items, onCancel, busy }: { items: ProgramApplication[]; onCancel: (a: ProgramApplication) => void; busy: boolean }) {
  if (items.length === 0) return <p className="text-sm text-slate-500">가상 신청 내역이 없습니다.</p>;
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.id} className="rounded border border-slate-200 p-2 text-sm">
          <p className="font-medium">{item.program?.title ?? '비공개로 전환된 프로그램'}</p>
          <p className="text-slate-600">
            {item.status === 'applied' ? '가상 신청함' : '신청 취소함'} · 심사 없음(시연) · {formatDate(item.created_at)}
          </p>
          {item.status === 'applied' && (
            <button type="button" disabled={busy} onClick={() => onCancel(item)} className="mt-1 rounded border px-2 py-0.5 text-xs disabled:opacity-50">신청 취소</button>
          )}
        </li>
      ))}
    </ul>
  );
}

function ProgramCard({ program, children }: { program: Program; children?: ReactNode }) {
  return (
    <li className="rounded border border-slate-200 p-3 text-sm">
      <ProvenanceBadge kind={program.provenance} checkedAt={program.checked_at} />
      <p className="mt-1 font-medium">{program.title}</p>
      <p className="text-slate-600">{program.host} · 신청 마감 {formatDate(program.apply_ends_at)}{program.capacity !== null && ` · 정원 ${program.capacity}`}</p>
      <p className="whitespace-pre-wrap">{program.summary}</p>
      <SourceLink url={program.source_url} />
      {children}
    </li>
  );
}

/** Public program list. Personal state (my applications, notes, notices, keys) lives only in
 * ProgramApplications, which the parent's `canApply=false` unmounts on 401/403. */
export function ProgramsPanel({ canApply, onAuthError }: { canApply: boolean; onAuthError: AuthHandler }) {
  const [programs, setPrograms] = useState<Load<{ items: Program[]; policyId: string }>>({ state: 'loading' });
  const alive = useAlive();

  const loadPrograms = useCallback(() => {
    setPrograms({ state: 'loading' });
    api.listPrograms().then(
      (data) => alive.current && setPrograms({ state: 'ready', data: { items: data.items, policyId: data.policy_id } }),
      (error) => alive.current && setPrograms({ state: 'error', ...describeError(error) }),
    );
  }, [alive]);
  useEffect(loadPrograms, [loadPrograms]);

  return (
    <section aria-labelledby="careers-programs" className="space-y-3">
      <h2 id="careers-programs" className="text-lg font-semibold">취업 프로그램 가상 신청</h2>
      <p className="text-xs text-slate-500">DEMO 프로그램만 가상 신청할 수 있습니다. 공개 원문 프로그램은 안내만 하며, 심사·선정·상담 기록은 제공하지 않습니다.</p>
      {programs.state === 'loading' && <Loading label="프로그램을 불러오는 중…" />}
      {programs.state === 'error' && <ErrorBox message={programs.message} requestId={programs.requestId} onRetry={loadPrograms} />}
      {programs.state === 'ready' && (
        <>
          <p className="text-xs text-slate-500">적용 규칙: 가상 시연 정책 {programs.data.policyId} (학교 규정 아님)</p>
          {programs.data.items.length === 0 && <p className="text-sm text-slate-500">등록된 프로그램이 없습니다.</p>}
          {!canApply && (
            <ul className="space-y-2">
              {programs.data.items.map((program) => <ProgramCard key={program.id} program={program} />)}
            </ul>
          )}
        </>
      )}
      {canApply && <ProgramApplications programs={programs.state === 'ready' ? programs.data.items : null} onAuthError={onAuthError} />}
    </section>
  );
}

function ProgramApplications({ programs, onAuthError }: { programs: Program[] | null; onAuthError: AuthHandler }) {
  const [mine, setMine] = useState<Load<ProgramApplication[]>>({ state: 'loading' });
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const alive = useAlive();
  const { failure, setFailure, fail } = useFailure('applications', onAuthError, alive);
  const intents = useRef(new Map<string, api.IntentKey>());

  const loadMine = useCallback(() => {
    if (!alive.current) return;
    setMine({ state: 'loading' });
    api.listApplications().then(
      (data) => alive.current && setMine({ state: 'ready', data }),
      (error) => {
        if (authCode(error)) onAuthError('applications', error);
        else if (alive.current) setMine({ state: 'error', ...describeError(error) });
      },
    );
  }, [alive, onAuthError]);
  useEffect(loadMine, [loadMine]);

  const intentFor = (programId: string) => {
    let intent = intents.current.get(programId);
    if (!intent) intents.current.set(programId, (intent = new api.IntentKey('apply')));
    return intent;
  };

  const apply = (program: Program) => {
    const note = (notes[program.id] ?? '').trim();
    const intent = intentFor(program.id);
    setBusy(true);
    setNotice(null);
    setFailure(null);
    api.applyToProgram(program.id, note, intent.keyFor({ program: program.id, note })).then(
      (created) => {
        if (!alive.current) return; // late success after 401/403: discard, no follow-up request
        intent.settle();
        setNotes((current) => ({ ...current, [program.id]: '' }));
        setNotice(created.status === 'applied' ? '가상 신청을 기록했습니다. 실제 접수·선정이 아닙니다.' : '이미 취소된 신청입니다.');
        loadMine();
      },
      fail,
    ).finally(() => alive.current && setBusy(false));
  };

  const cancel = (application: ProgramApplication) => {
    setBusy(true);
    setNotice(null);
    setFailure(null);
    api.cancelApplication(application).then(
      () => {
        if (!alive.current) return;
        setNotice('가상 신청을 취소했습니다.');
        loadMine();
      },
      fail,
    ).finally(() => alive.current && setBusy(false));
  };

  const activeIds = new Set(mine.state === 'ready' ? mine.data.filter((a) => a.status === 'applied').map((a) => a.program_id) : []);

  return (
    <>
      {programs && (
        <ul className="space-y-2">
          {programs.map((program) => (
            <ProgramCard key={program.id} program={program}>
              {program.accepts_virtual_application && !activeIds.has(program.id) && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <input aria-label={`${program.title} 메모`} maxLength={200} value={notes[program.id] ?? ''} onChange={(e) => setNotes({ ...notes, [program.id]: e.target.value })} className="rounded border px-2 py-1" />
                  <button type="button" disabled={busy || !program.window_open} onClick={() => apply(program)} className="rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-50">가상 신청</button>
                </div>
              )}
            </ProgramCard>
          ))}
        </ul>
      )}
      {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
      {failure && <ErrorBox message={failure.message} requestId={failure.requestId} />}
      <div className="space-y-2">
        <h3 className="font-medium">내 가상 신청</h3>
        {mine.state === 'loading' && <Loading label="내 신청을 불러오는 중…" />}
        {mine.state === 'error' && <ErrorBox message={mine.message} requestId={mine.requestId} onRetry={loadMine} />}
        {mine.state === 'ready' && <MyApplications items={mine.data} onCancel={cancel} busy={busy} />}
      </div>
    </>
  );
}

// ------------------------------------------------------------ FR-JOB-004 employer drafts

const EMPLOYMENT_LABEL: Record<EmploymentType, string> = {
  full_time: '정규직', part_time: '아르바이트', internship: '인턴', contract: '계약직',
};

type DraftForm = { company_alias: string; role_title: string; description: string; employment_type: EmploymentType; closes_on: string };
const EMPTY_DRAFT: DraftForm = { company_alias: '', role_title: '', description: '', employment_type: 'internship', closes_on: '' };

function closesAt(day: string): string {
  // Date input is a KST calendar day; send an explicit offset so the server receives aware time.
  return `${day}T23:59:00+09:00`;
}

export function EmployerDraftPanel({ onAuthError }: { onAuthError: AuthHandler }) {
  const [drafts, setDrafts] = useState<Load<EmployerDraft[]>>({ state: 'loading' });
  const [form, setForm] = useState<DraftForm>(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const alive = useAlive();
  const { failure, setFailure, fail } = useFailure('employer', onAuthError, alive);
  const intent = useRef(new api.IntentKey('draft'));

  const load = useCallback(() => {
    if (!alive.current) return;
    setDrafts({ state: 'loading' });
    api.listEmployerDrafts().then(
      (data) => alive.current && setDrafts({ state: 'ready', data }),
      (error) => {
        if (authCode(error)) onAuthError('employer', error);
        else if (alive.current) setDrafts({ state: 'error', ...describeError(error) });
      },
    );
  }, [alive, onAuthError]);
  useEffect(load, [load]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const { closes_on, ...rest } = form;
    const input = { ...rest, company_alias: rest.company_alias.trim(), role_title: rest.role_title.trim(), description: rest.description.trim(), closes_at: closesAt(closes_on) };
    setBusy(true);
    setNotice(null);
    setFailure(null);
    api.createEmployerDraft(input, intent.current.keyFor(input)).then(
      () => {
        if (!alive.current) return;
        intent.current.settle();
        setForm(EMPTY_DRAFT);
        setNotice('초안을 저장했습니다. 제출·게시되지 않습니다.');
        load();
      },
      fail,
    ).finally(() => alive.current && setBusy(false));
  };

  const remove = (draft: EmployerDraft) => {
    setBusy(true);
    setNotice(null);
    setFailure(null);
    api.deleteEmployerDraft(draft).then(
      () => {
        if (!alive.current) return;
        setNotice('초안을 삭제했습니다.');
        load();
      },
      fail,
    ).finally(() => alive.current && setBusy(false));
  };

  return (
    <section aria-labelledby="careers-employer" className="space-y-3">
      <h2 id="careers-employer" className="text-lg font-semibold">기업 채용의뢰 초안</h2>
      <p className="text-xs text-slate-500">초안만 저장합니다. 기업 회원·제출·검토·공고 게시는 운영 승인 전까지 제공하지 않습니다.</p>
      {drafts.state === 'loading' && <Loading label="초안을 불러오는 중…" />}
      {drafts.state === 'error' && <ErrorBox message={drafts.message} requestId={drafts.requestId} onRetry={load} />}
      {drafts.state === 'ready' && (
        <>
          {drafts.data.length === 0 && <p className="text-sm text-slate-500">저장된 초안이 없습니다.</p>}
          <ul className="space-y-2">
            {drafts.data.map((draft) => (
              <li key={draft.id} className="rounded border border-slate-200 p-2 text-sm">
                <p className="font-medium">{draft.role_title} · {draft.company_alias}</p>
                <p className="text-slate-600">{EMPLOYMENT_LABEL[draft.employment_type]} · 마감 {formatDate(draft.closes_at)} · 초안(게시 안 됨)</p>
                <button type="button" disabled={busy} onClick={() => remove(draft)} className="mt-1 rounded border px-2 py-0.5 text-xs disabled:opacity-50">삭제</button>
              </li>
            ))}
          </ul>
          <form onSubmit={submit} className="grid gap-2 text-sm">
            <label className="flex flex-col">가상 기업명
              <input required minLength={2} maxLength={30} value={form.company_alias} onChange={(e) => setForm({ ...form, company_alias: e.target.value })} className="rounded border px-2 py-1" />
            </label>
            <label className="flex flex-col">직무명
              <input required minLength={2} maxLength={80} value={form.role_title} onChange={(e) => setForm({ ...form, role_title: e.target.value })} className="rounded border px-2 py-1" />
            </label>
            <label className="flex flex-col">설명
              <textarea required maxLength={2000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="rounded border px-2 py-1" />
            </label>
            <label className="flex flex-col">고용 형태
              <select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value as EmploymentType })} className="rounded border px-2 py-1">
                {Object.entries(EMPLOYMENT_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="flex flex-col">마감일
              <input required type="date" value={form.closes_on} onChange={(e) => setForm({ ...form, closes_on: e.target.value })} className="rounded border px-2 py-1" />
            </label>
            <button type="submit" disabled={busy} className="justify-self-start rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-50">초안 저장</button>
          </form>
        </>
      )}
      {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
      {failure && <ErrorBox message={failure.message} requestId={failure.requestId} />}
    </section>
  );
}
