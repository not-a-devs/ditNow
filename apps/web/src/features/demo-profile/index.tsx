import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ApiError } from '../../lib/api';
import { canonical, INTERESTS, loadDemoProfile, saveDemoProfile, SKILL_LEVELS, type DemoPreferences, type Interest, type Preferences, type SkillLevel } from './api';

const INTEREST_LABELS: Record<Interest, string> = { coding: '코딩', design: '디자인', volunteering: '봉사', career: '진로' };
const LEVEL_LABELS: Record<SkillLevel, string> = { beginner: '입문', intermediate: '중급' };
const EMPTY: Preferences = { interests: [], skill_level: 'beginner' };
const same = (a: Preferences, b: Preferences) => a.skill_level === b.skill_level && canonical(a.interests).join() === canonical(b.interests).join();
const summary = (value: Preferences) => `관심 활동: ${canonical(value.interests).map(item => INTEREST_LABELS[item]).join(', ') || '없음'} · 수준: ${LEVEL_LABELS[value.skill_level]}`;
const isAuth = (error: unknown) => error instanceof ApiError && (error.status === 401 || error.status === 403);
const message = (error: unknown) => error instanceof ApiError && error.status === 503
  ? '가상 활동 설정 저장소 또는 공통 로그인 연결이 준비되지 않았거나 시연 수용 한도에 도달했습니다.'
  : error instanceof ApiError && error.status === 409 ? '다른 화면에서 먼저 변경되었습니다. 입력은 보존했습니다. 다시 조회하면 입력이 대체됩니다.'
  : error instanceof ApiError && error.status === 401 ? '로그인이 만료되어 개인 설정 화면을 지웠습니다.'
  : error instanceof ApiError && error.status === 403 ? '현재 계정으로 접근할 수 없어 개인 설정 화면을 지웠습니다.'
  : error instanceof ApiError && error.status === 400 ? '허용된 선택지만 저장할 수 있습니다.'
  : error instanceof ApiError && error.code === 'INVALID_RESPONSE' ? '서버 응답의 형식을 확인하지 못했습니다.'
  : '결과를 확인하지 못했습니다. 다시 조회해 저장 여부를 확인해 주세요.';

/** Shared auth owner must change this generation (or remount) on account/session changes. */
export default function DemoProfile({ sessionGeneration = 0 }: { sessionGeneration?: number }) {
  // A new generation is a new instance: old account state is dropped during commit.
  return <DemoProfileSession key={sessionGeneration} />;
}

function DemoProfileSession() {
  const [saved, setSaved] = useState<DemoPreferences | null>(null), [draft, setDraft] = useState<Preferences>(EMPTY);
  const [pending, setPending] = useState<'read' | 'write' | null>('read'), [confirming, setConfirming] = useState(false);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const alive = useRef(false), epoch = useRef(0), busy = useRef(false), lockedRef = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useLayoutEffect(() => {
    alive.current = true;
    return () => { alive.current = false; epoch.current++; busy.current = false; controller.current?.abort(); controller.current = null; };
  }, []);

  function apply(data: DemoPreferences) { setSaved(data); setDraft({ interests: canonical(data.interests), skill_level: data.skill_level }); }
  function clear() { setSaved(null); setDraft(EMPTY); setConfirming(false); }
  /** Same-tick latch: returns null when a request is in flight, the instance is gone, or auth is locked. */
  function begin(kind: 'read' | 'write') {
    if (!alive.current || lockedRef.current || busy.current) return null;
    busy.current = true; controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    setPending(kind); setError(''); setNotice(''); return { version: ++epoch.current, request };
  }
  const current = (version: number, request: AbortController) => alive.current && !lockedRef.current && version === epoch.current && !request.signal.aborted;
  function finish(version: number) { if (alive.current && version === epoch.current) { busy.current = false; controller.current = null; setPending(null); } }
  function fail(cause: unknown) {
    setError(message(cause));
    if (!isAuth(cause)) return;
    // 401/403 latches for this generation; only a new generation (new instance) may read again.
    lockedRef.current = true; busy.current = false; epoch.current++; controller.current?.abort(); controller.current = null;
    setLocked(true); setPending(null); setNotice(''); clear();
  }
  async function load() {
    const run = begin('read'); if (!run) return;
    const { version, request } = run; clear();
    try { const data = await loadDemoProfile(request.signal); if (current(version, request)) apply(data); }
    catch (cause) { if (current(version, request)) fail(cause); }
    finally { finish(version); }
  }
  useEffect(() => { void load(); }, []);
  async function save() {
    if (!saved) return;
    const body = { ...draft, revision: saved.revision };
    const run = begin('write'); if (!run) return;
    const { version, request } = run; setConfirming(false);
    try {
      const written = await saveDemoProfile(body, request.signal);
      if (!current(version, request)) return;
      if (written.revision !== body.revision + 1 || !same(written, body)) throw new ApiError('INVALID_RESPONSE', 200);
      const readback = await loadDemoProfile(request.signal);
      if (!current(version, request)) return;
      if (readback.revision < written.revision || (readback.revision === written.revision && !same(readback, written)))
        throw new ApiError('INVALID_RESPONSE', 200);
      apply(readback);
      setNotice(readback.revision === written.revision && same(readback, written)
        ? '저장 후 다시 조회해 같은 값을 확인했습니다. 프로세스 메모리에만 있어 서버 재시작 시 초기화됩니다.'
        : '저장 직후 다른 변경이 있어 최신 값을 표시합니다.');
    } catch (cause) { if (current(version, request)) fail(cause); }
    finally { finish(version); }
  }
  function toggle(item: Interest, checked: boolean) {
    setConfirming(false); setNotice('');
    setDraft(value => ({ ...value, interests: canonical(checked ? [...value.interests, item] : value.interests.filter(entry => entry !== item)) }));
  }
  const disabled = pending !== null || locked || !saved, dirty = !!saved && !same(draft, saved);
  return <section className="mx-auto grid max-w-3xl gap-4 p-4" aria-labelledby="demo-profile-title">
    <header><h1 id="demo-profile-title" className="text-2xl font-semibold">가상 활동 선호 설정</h1>
      <p>가상 계정(DEMO)용 체험 설정입니다. 실명·학과·학년·역할 등 신원 정보는 다루지 않으며 변경할 수 없습니다.</p></header>
    <p className="rounded bg-amber-50 p-3" role="note">한계: 이 설정은 서버 프로세스 메모리(PROCESS_MEMORY)에만 보관됩니다. 데이터베이스에 저장되지 않으며 서버 재시작 시 초기화되고, 실제 권한이나 공개 프로필에 반영되지 않습니다.</p>
    <button type="button" disabled={pending !== null || locked} className="rounded border p-3" onClick={() => void load()}>다시 조회 · 현재 입력 대체</button>
    {pending === 'read' && <p role="status">현재 계정의 설정을 확인 중…</p>}
    {pending === 'write' && <p role="status">저장 후 다시 조회해 확인 중…</p>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {saved && !locked && <>
      <p>저장된 값 · 개정 {saved.revision} · {summary(saved)}</p>
      <fieldset className="grid gap-2 rounded border p-3" disabled={disabled}>
        <legend>관심 활동 (고정 선택지)</legend>
        {INTERESTS.map(item => <label key={item} className="flex gap-2"><input type="checkbox" checked={draft.interests.includes(item)} onChange={event => toggle(item, event.target.checked)} />{INTEREST_LABELS[item]}</label>)}
      </fieldset>
      <fieldset className="grid gap-2 rounded border p-3" disabled={disabled}>
        <legend>활동 수준</legend>
        {SKILL_LEVELS.map(level => <label key={level} className="flex gap-2"><input type="radio" name="demo-skill-level" checked={draft.skill_level === level} onChange={() => { setConfirming(false); setNotice(''); setDraft(value => ({ ...value, skill_level: level })); }} />{LEVEL_LABELS[level]}</label>)}
      </fieldset>
      {!confirming
        ? <button type="button" disabled={disabled || !dirty} className="rounded bg-blue-700 p-3 text-white" onClick={() => setConfirming(true)}>변경 내용 확인</button>
        : <div className="grid gap-2 rounded border p-3" role="group" aria-label="저장 확인">
          <p>{summary(draft)} 으로 저장할까요?</p>
          <button type="button" disabled={disabled} className="rounded bg-blue-700 p-3 text-white" onClick={() => void save()}>저장 확정</button>
          <button type="button" disabled={disabled} className="rounded border p-3" onClick={() => setConfirming(false)}>계속 편집</button>
        </div>}
    </>}
  </section>;
}
