// DEMO attendance client over the shared requestData<T> (src/lib/api.ts), which prefixes the
// configured base (default /api/v1). Paths are relative to that base. The server resolves the
// caller from the common session; nothing here sends a user, department or role.
import { requestData } from '../../lib/api';

export const DEMO_CODE_PATTERN = /^[0-9]{6}$/;

export interface DemoCardView {
  card: {
    mode: 'DEMO';
    storage: 'PROCESS_MEMORY';
    display_alias: string;
    card_label: string;
    valid_credential: false;
    qr_enabled: false;
    notice: string;
  };
  session: {
    session_label: string;
    method: 'NUMERIC_CODE_SIMULATION';
    simulation_code: string;
    notice: string;
  };
}

export interface DemoAttendanceState {
  mode: 'DEMO';
  storage: 'PROCESS_MEMORY';
  method: 'NUMERIC_CODE_SIMULATION';
  checked_in: boolean;
  checked_in_at: string | null;
}

export interface DemoCheckInResult {
  mode: 'DEMO';
  storage: 'PROCESS_MEMORY';
  method: 'NUMERIC_CODE_SIMULATION';
  checked_in_at: string;
  replayed: boolean;
}

const BASE = '/me/demo-attendance';

function invalid(): never {
  throw new Error('시연 응답 형식이 올바르지 않습니다.');
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : invalid();
}

function text(value: unknown): string {
  return typeof value === 'string' && value.length <= 500 ? value : invalid();
}

function demoTags(value: Record<string, unknown>): void {
  if (value.mode !== 'DEMO' || value.storage !== 'PROCESS_MEMORY') invalid();
}

function method(value: Record<string, unknown>): void {
  if (value.method !== 'NUMERIC_CODE_SIMULATION') invalid();
}

function timestamp(value: unknown): string {
  const at = text(value);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(at)) invalid();
  const parsed = new Date(at);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 19) !== at.slice(0, 19)) invalid();
  return at;
}

export function parseCard(value: unknown): DemoCardView {
  const root = record(value);
  const card = record(root.card);
  const session = record(root.session);
  demoTags(card);
  if (card.valid_credential !== false || card.qr_enabled !== false) invalid();
  if (session.method !== 'NUMERIC_CODE_SIMULATION') invalid();
  const code = text(session.simulation_code);
  if (!DEMO_CODE_PATTERN.test(code)) invalid();
  return {
    card: {
      mode: 'DEMO',
      storage: 'PROCESS_MEMORY',
      display_alias: text(card.display_alias),
      card_label: text(card.card_label),
      valid_credential: false,
      qr_enabled: false,
      notice: text(card.notice),
    },
    session: {
      session_label: text(session.session_label),
      method: 'NUMERIC_CODE_SIMULATION',
      simulation_code: code,
      notice: text(session.notice),
    },
  };
}

export function parseState(value: unknown): DemoAttendanceState {
  const root = record(value);
  demoTags(root);
  method(root);
  if (typeof root.checked_in !== 'boolean') invalid();
  const at = root.checked_in_at === null ? null : timestamp(root.checked_in_at);
  if (root.checked_in !== (at !== null)) invalid();
  return { mode: 'DEMO', storage: 'PROCESS_MEMORY', method: 'NUMERIC_CODE_SIMULATION', checked_in: root.checked_in, checked_in_at: at };
}

export function parseCheckIn(value: unknown): DemoCheckInResult {
  const root = record(value);
  demoTags(root);
  method(root);
  if (typeof root.replayed !== 'boolean') invalid();
  return {
    mode: 'DEMO',
    storage: 'PROCESS_MEMORY',
    method: 'NUMERIC_CODE_SIMULATION',
    checked_in_at: timestamp(root.checked_in_at),
    replayed: root.replayed,
  };
}

export async function getDemoCard(signal?: AbortSignal): Promise<DemoCardView> {
  return parseCard(await requestData<unknown>(`${BASE}/card`, { signal }));
}

export async function getDemoState(signal?: AbortSignal): Promise<DemoAttendanceState> {
  return parseState(await requestData<unknown>(`${BASE}/state`, { signal }));
}

export async function checkInDemo(code: string, signal?: AbortSignal): Promise<DemoCheckInResult> {
  return parseCheckIn(
    await requestData<unknown>(`${BASE}/check-in`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
      signal,
    }),
  );
}
