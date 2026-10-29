import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../../lib/api';
import { calculateTravel, kstInput, NOTICE, type TravelResult } from './api';

const labels = { OVERLAP: '수업 시각이 겹칩니다', INSUFFICIENT: '입력한 예상 이동 시간보다 부족합니다', NO_MARGIN: '계산상 추가 여유가 없습니다', HAS_MARGIN: '입력 기준 이동 후 여유가 있습니다' };
const duration = (seconds: number) => `${Math.abs(seconds) / 60}분`;
const errorMessage = (e: unknown) => e instanceof ApiError && e.status === 503 ? '이동 계산 API 연결을 준비하고 있습니다. 입력값을 확인한 뒤 다시 시도하세요.'
  : e instanceof ApiError && e.code === 'INVALID_RESPONSE' ? '응답의 출처와 계산값을 확인하지 못했습니다. 다시 계산하세요.'
  : e instanceof ApiError ? e.message : '계산 결과를 확인하지 못했습니다. 다시 시도하세요.';

export default function CampusTravelPage() {
  const [previous, setPrevious] = useState(''), [next, setNext] = useState(''), [minutes, setMinutes] = useState('');
  const [result, setResult] = useState<TravelResult | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const alive = useRef(true), epoch = useRef(0), pending = useRef<AbortController | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; epoch.current++; pending.current?.abort(); }; }, []);
  function changed(set: (value: string) => void, value: string) {
    epoch.current++; pending.current?.abort(); set(value); setResult(null); setError(''); setBusy(false);
  }
  async function submit() {
    const version = ++epoch.current; pending.current?.abort(); const controller = new AbortController(); pending.current = controller;
    setResult(null); setError(''); setBusy(true);
    try {
      const input = kstInput(previous, next, minutes);
      const data = await calculateTravel(input, controller.signal);
      if (alive.current && version === epoch.current && !controller.signal.aborted) setResult(data);
    } catch (e) {
      if (alive.current && version === epoch.current && !controller.signal.aborted) setError(errorMessage(e));
    } finally { if (alive.current && version === epoch.current) setBusy(false); }
  }
  return <section aria-labelledby="travel-title" className="mx-auto flex max-w-2xl flex-col gap-4 p-4">
    <header><h1 id="travel-title" className="text-2xl font-semibold">강의 간 이동 여유 계산</h1><p>학교 시간표를 불러오지 않고 직접 입력한 값으로 계산합니다.</p></header>
    <p className="rounded bg-amber-50 p-3">{NOTICE}</p>
    <p>모든 입력 시각은 한국 표준시(KST, UTC+09:00)입니다. 입력값은 저장하지 않습니다.</p>
    <form onSubmit={e => { e.preventDefault(); void submit(); }} className="flex flex-col gap-3">
      <label>앞 수업 종료 시각 (KST)<input required type="datetime-local" value={previous} onChange={e => changed(setPrevious, e.target.value)} className="block w-full rounded border p-2" /></label>
      <label>다음 수업 시작 시각 (KST)<input required type="datetime-local" value={next} onChange={e => changed(setNext, e.target.value)} className="block w-full rounded border p-2" /></label>
      <label>내가 예상한 이동 시간 (분)<input required type="number" min="0" max="1440" step="1" value={minutes} onChange={e => changed(setMinutes, e.target.value)} className="block w-full rounded border p-2" /></label>
      <p>기술적 입력 한도: 2000~2099년, 두 시각 차이 최대 7일, 예상 이동 0~1440분 정수. 학교 최소 이동 기준이 아닙니다.</p>
      <button disabled={busy} className="rounded bg-blue-700 p-2 text-white">{busy ? '계산 중…' : '입력 기준으로 계산'}</button>
    </form>
    {busy && <p role="status">계산 결과를 확인하고 있어요…</p>}
    {error && <p role="alert">{error}</p>}
    {result && <div role="status" className="rounded border p-3"><h2>{labels[result.status]}</h2><p>수업 간 간격: {result.gap_seconds < 0 ? '겹침 ' : ''}{duration(result.gap_seconds)}</p><p>내 예상 이동 시간: {duration(result.travel_seconds)}</p><p>{result.remaining_seconds < 0 ? '부족' : '남는 시간'}: {duration(result.remaining_seconds)}</p><p>예상 시간 출처: 사용자 입력(USER_INPUT) · 계산 버전 {result.calculation_version}</p><p>계산상 여유는 실제 도착을 보장하지 않습니다.</p></div>}
    {!busy && !error && !result && <p>두 시각과 예상 이동 시간을 입력해 주세요.</p>}
  </section>;
}
