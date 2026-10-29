import { ApiError, requestData } from '../../lib/api';

export const NOTICE = '사용자가 입력한 시각과 예상 이동 시간만 계산합니다. 실제 지도·최단 경로·공식 이동 시간·접근 가능한 동선·도착을 보장하지 않습니다. 개인 시간표는 연결하지 않습니다.';
export type TravelInput = { previous_ends_at: string; next_starts_at: string; estimated_travel_minutes: number };
export type TravelResult = {
  previous_ends_at: string; next_starts_at: string; gap_seconds: number; travel_seconds: number;
  remaining_seconds: number; status: 'OVERLAP' | 'INSUFFICIENT' | 'NO_MARGIN' | 'HAS_MARGIN';
  estimate_source: 'USER_INPUT'; calculation_version: 'manual-travel-v1'; notice: typeof NOTICE;
};

function timestamp(value: unknown): number {
  if (typeof value !== 'string') return NaN;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match) return NaN;
  const [, y, m, d, h, min, s] = match;
  const maxDay = new Date(Date.UTC(+y, +m, 0)).getUTCDate();
  if (+m < 1 || +m > 12 || +d < 1 || +d > maxDay || +h > 23 || +min > 59 || +s > 59) return NaN;
  return Date.parse(value);
}

export function validateInput(input: TravelInput): void {
  const start = timestamp(input.previous_ends_at), end = timestamp(input.next_starts_at);
  if (!/^20\d{2}-/.test(input.previous_ends_at) || !/^20\d{2}-/.test(input.next_starts_at)
    || !Number.isFinite(start) || !Number.isFinite(end) || Math.abs(end - start) > 604800000
    || !Number.isInteger(input.estimated_travel_minutes) || input.estimated_travel_minutes < 0 || input.estimated_travel_minutes > 1440) {
    throw new ApiError('VALIDATION', 400);
  }
}

/** datetime-local is explicitly KST here, independent of the browser's local zone. */
export function kstInput(previous: string, next: string, minutes: string): TravelInput {
  if (!/^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(previous)
    || !/^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(next) || !/^\d{1,4}$/.test(minutes)) throw new ApiError('VALIDATION', 400);
  const input = { previous_ends_at: `${previous}:00+09:00`, next_starts_at: `${next}:00+09:00`, estimated_travel_minutes: Number(minutes) };
  validateInput(input);
  return input;
}

export async function calculateTravel(input: TravelInput, signal?: AbortSignal): Promise<TravelResult> {
  validateInput(input);
  const raw = await requestData<unknown>('/campus-travel/calculate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal, cache: 'no-store',
  });
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new ApiError('INVALID_RESPONSE', 200);
  const v = raw as Record<string, unknown>;
  const gap = (timestamp(input.next_starts_at) - timestamp(input.previous_ends_at)) / 1000;
  const travel = input.estimated_travel_minutes * 60, remaining = gap - travel;
  const status = gap < 0 ? 'OVERLAP' : remaining < 0 ? 'INSUFFICIENT' : remaining === 0 ? 'NO_MARGIN' : 'HAS_MARGIN';
  const keys = ['previous_ends_at', 'next_starts_at', 'gap_seconds', 'travel_seconds', 'remaining_seconds', 'status', 'estimate_source', 'calculation_version', 'notice'];
  if (Object.keys(v).length !== keys.length || !keys.every(key => Object.hasOwn(v, key))
    || timestamp(v.previous_ends_at) !== timestamp(input.previous_ends_at) || timestamp(v.next_starts_at) !== timestamp(input.next_starts_at)
    || v.gap_seconds !== gap || v.travel_seconds !== travel || v.remaining_seconds !== remaining || v.status !== status
    || v.estimate_source !== 'USER_INPUT' || v.calculation_version !== 'manual-travel-v1' || v.notice !== NOTICE) throw new ApiError('INVALID_RESPONSE', 200);
  return v as TravelResult;
}
