import type { Database } from '../types';
import { createSeed, DB_VERSION } from './seed';

// 사전 MVP 저장소: 서버 DB 대신 브라우저 localStorage에 영속한다.
// 같은 브라우저의 다른 탭과는 BroadcastChannel/storage 이벤트로 실시간 동기화한다.
// 서버(Supabase) 연결 시 이 파일과 api.ts 내부만 교체하는 것을 목표로 한다.

const DB_KEY = 'ditnow.db.v1';
const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('ditnow-db') : null;
const listeners = new Set<() => void>();

let cache: Database | null = null;

function load(): Database {
  try {
    const raw = localStorage.getItem(DB_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Database;
      if (parsed.version === DB_VERSION) return parsed;
    }
  } catch {
    // 손상되었거나 접근 불가 → 시드로 복구
  }
  const seed = createSeed();
  persist(seed);
  return seed;
}

function persist(db: Database) {
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(db));
  } catch {
    // 사파리 프라이빗 모드 등 저장 불가 — 메모리 캐시로만 동작
  }
}

function notify() {
  listeners.forEach((l) => l());
}

export function readDb(): Database {
  if (!cache) cache = load();
  return cache;
}

/** 단일 트랜잭션처럼 동작: fn이 throw하면 아무것도 저장하지 않는다 */
export function transact<T>(fn: (draft: Database) => T): T {
  const draft = structuredClone(readDb());
  const result = fn(draft);
  cache = draft;
  persist(draft);
  notify();
  channel?.postMessage('changed');
  return result;
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function resetDb() {
  cache = createSeed();
  persist(cache);
  notify();
  channel?.postMessage('changed');
}

function reloadFromStorage() {
  cache = null;
  notify();
}

channel?.addEventListener('message', reloadFromStorage);
window.addEventListener('storage', (e) => {
  if (e.key === DB_KEY) reloadFromStorage();
});

export function uid(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

export const nowIso = () => new Date().toISOString();
