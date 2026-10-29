import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../lib/api';
import { intentTracker, loadProfile, saveProfile, type Profile } from './api';

const EMPTY = { skills: '', interests: '', bio: '' };
// Server tags reject CR/LF, so line boundaries preserve commas inside a single tag.
const split = (value: string) => value.split(/\r?\n/).map(item => item.trim()).filter(Boolean);
const message = (error: unknown) => error instanceof ApiError && error.status === 503
  ? '공통 신원·프로필 원장과 편집 정책 연결을 준비하고 있습니다.'
  : error instanceof ApiError && error.status === 404 ? '현재 계정의 승인된 프로필이 없습니다. 자동 생성하지 않습니다.'
  : error instanceof ApiError && error.status === 409 ? '프로필 또는 편집 정책이 변경되었습니다. 입력은 보존했습니다. 다시 조회하면 입력이 대체됩니다.'
  : error instanceof ApiError && error.status === 401 ? '로그인이 만료되어 개인 프로필을 지웠습니다.'
  : error instanceof ApiError && error.status === 403 ? '현재 프로필 편집 권한이 없어 개인 화면을 지웠습니다.'
  : error instanceof ApiError && error.code === 'INVALID_RESPONSE' ? '프로필의 출처·공개 필드를 확인하지 못했습니다.'
  : '저장 결과를 확인하지 못했습니다. 같은 입력으로 재시도하거나 원장을 다시 조회해 주세요.';

/** Shared auth owner must change this generation (or remount) on account/session changes. */
export default function ProfilePage({ sessionGeneration = 0 }: { sessionGeneration?: number }) {
  const [profile, setProfile] = useState<Profile | null>(null), [form, setForm] = useState(EMPTY);
  const [pending, setPending] = useState<'read' | 'write' | null>('read');
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const alive = useRef(false), epoch = useRef(0), busy = useRef(false), controller = useRef<AbortController | null>(null);
  const intent = useRef(intentTracker());
  function apply(data: Profile) { setProfile(data); setForm({ skills: data.skills.join('\n'), interests: data.interests.join('\n'), bio: data.bio }); }
  function fail(cause: unknown) {
    setError(message(cause));
    if (cause instanceof ApiError && [401, 403].includes(cause.status)) { setProfile(null); setForm(EMPTY); intent.current.clear(); }
  }
  async function load() {
    const version = ++epoch.current; controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    busy.current = true; setPending('read'); setError(''); setNotice(''); setProfile(null); setForm(EMPTY); intent.current.clear();
    try { const data = await loadProfile(request.signal); if (alive.current && version === epoch.current && !request.signal.aborted) apply(data); }
    catch (cause) { if (alive.current && version === epoch.current && !request.signal.aborted) fail(cause); }
    finally { if (alive.current && version === epoch.current) { busy.current = false; setPending(null); } }
  }
  useEffect(() => {
    alive.current = true; void load();
    return () => { alive.current = false; epoch.current++; controller.current?.abort(); };
  }, [sessionGeneration]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!profile || busy.current) return;
    const body = { skills: profile.policy.editable_fields.includes('skills') ? split(form.skills) : profile.skills,
      interests: profile.policy.editable_fields.includes('interests') ? split(form.interests) : profile.interests,
      bio: profile.policy.editable_fields.includes('bio') ? form.bio : profile.bio,
      expected_revision: profile.revision, expected_policy_revision: profile.policy.revision };
    const version = ++epoch.current, request = new AbortController(); controller.current = request;
    busy.current = true; setPending('write'); setError(''); setNotice('');
    try {
      const data = await saveProfile(body, intent.current.key(body), request.signal);
      if (!alive.current || version !== epoch.current || request.signal.aborted) return;
      intent.current.clear(); apply(data); setNotice(data.replayed ? '같은 요청의 현재 프로필을 확인했습니다.' : '개인 활동 필드를 저장했습니다. 실명·학적·권한은 변경하지 않았습니다.');
    } catch (cause) { if (alive.current && version === epoch.current && !request.signal.aborted) fail(cause); }
    finally { if (alive.current && version === epoch.current) { busy.current = false; setPending(null); } }
  }
  const allowed = (field: 'skills' | 'interests' | 'bio') => profile?.policy.editable_fields.includes(field) ?? false;
  return <section className="mx-auto grid max-w-3xl gap-4 p-4" aria-labelledby="profile-title">
    <header><h1 id="profile-title" className="text-2xl font-semibold">내 활동 프로필</h1><p>가상 계정(DEMO)의 개인 활동 필드입니다. 실명 협업 신원과 학교 인증을 새로 만들지 않습니다.</p></header>
    <p className="rounded bg-amber-50 p-3">본인 전용 화면입니다. 실제 연락처·민감 정보를 입력하지 마세요. 공개 모집 프로필로 자동 배포하지 않습니다.</p>
    <button disabled={pending !== null} className="rounded border p-3" onClick={() => void load()}>프로필 다시 조회 · 현재 입력 대체</button>
    {pending === 'read' && <p role="status">현재 계정과 편집 정책을 확인 중…</p>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {profile && <>
      <dl className="grid gap-2 rounded border p-3"><dt>현재 원장의 표시 실명 · 읽기 전용</dt><dd>{profile.display_name}</dd><dt>현재 학과·학년 · 읽기 전용</dt><dd>{profile.department_name} · {profile.academic_year}학년</dd></dl>
      <p>가상 프로필 개정 {profile.revision} · 승인된 편집 정책 개정 {profile.policy.revision}. 역할·계정 상태·학적 변경 기능은 없습니다.</p>
      {!profile.policy.editable_fields.length && <p>현재 승인된 편집 가능 필드가 없습니다. 조회만 가능합니다.</p>}
      <form className="grid gap-3" onSubmit={event => void submit(event)}>
        <label className="grid gap-1">기술 · 한 줄에 한 항목<textarea className="rounded border p-2" value={form.skills} disabled={pending !== null || !allowed('skills')} onChange={event => setForm(value => ({ ...value, skills: event.target.value }))} /></label>
        <label className="grid gap-1">관심사 · 한 줄에 한 항목<textarea className="rounded border p-2" value={form.interests} disabled={pending !== null || !allowed('interests')} onChange={event => setForm(value => ({ ...value, interests: event.target.value }))} /></label>
        <label className="grid gap-1">가상 소개<textarea className="rounded border p-2" value={form.bio} disabled={pending !== null || !allowed('bio')} onChange={event => setForm(value => ({ ...value, bio: event.target.value }))} /></label>
        <p>기술·관심사 각각20개, 항목당30자, 소개500자. 오류 후 같은 입력은 같은 요청 키로 확인하며 입력을 바꾸면 새 의도로 보냅니다.</p>
        <button disabled={pending !== null || !profile.policy.editable_fields.length} className="rounded bg-blue-700 p-3 text-white">{pending === 'write' ? '저장 확인 중…' : '활동 필드 저장'}</button>
      </form>
    </>}
  </section>;
}
