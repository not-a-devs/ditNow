import type { CheckItem, Database, Opportunity, OpportunityKind, SavedOpportunity, SavedStatus, User } from '../../types';
import { readDb, transact, uid, nowIso } from '../store';
import { ApiError, assertValid, latency, notFound, requireUser, text } from './core';

// 기회 센터 + 개인 준비상태 (FR-OPP-002~004).
// 외부 기관 제출 여부는 자동 검증 불가 — 'self_reported_submitted'는 학생 본인 기록일 뿐이다 (DFLT-006).

export const OPPORTUNITY_KINDS: OpportunityKind[] = ['장학금', '근로', '공모전', '취업', '행사'];

export interface OpportunityView extends Opportunity {
  saved: SavedOpportunity | null;
  isClosed: boolean;
}

function view(db: Database, user: User, o: Opportunity): OpportunityView {
  return {
    ...o,
    saved: db.saved.find((s) => s.userId === user.id && s.opportunityId === o.id) ?? null,
    isClosed: new Date(o.deadline).getTime() < Date.now(),
  };
}

export function listOpportunities(kind?: OpportunityKind) {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    return db.opportunities
      .filter((o) => !kind || o.kind === kind)
      .sort((a, b) => a.deadline.localeCompare(b.deadline))
      .map((o) => view(db, user, o));
  });
}

export function getOpportunity(id: string) {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    const o = db.opportunities.find((x) => x.id === id);
    if (!o) notFound('공고');
    const v = view(db, user, o);
    const items = v.saved
      ? db.checkItems.filter((c) => c.savedId === v.saved!.id).sort((a, b) => a.sortOrder - b.sortOrder)
      : [];
    return { opportunity: v, items };
  });
}

/** 본인 저장 항목만 — 다른 학생 상태 접근 불가 */
function requireOwnSaved(db: Database, user: User, savedId: string) {
  const s = db.saved.find((x) => x.id === savedId);
  if (!s || s.userId !== user.id) notFound('저장한 공고');
  return s;
}

export function saveOpportunity(opportunityId: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const o = db.opportunities.find((x) => x.id === opportunityId);
      if (!o) notFound('공고');
      const existing = db.saved.find((s) => s.userId === user.id && s.opportunityId === opportunityId);
      if (existing) return existing; // (user_id, opportunity_id) unique — 멱등
      const at = nowIso();
      const saved: SavedOpportunity = {
        id: uid('s'), userId: user.id, opportunityId, status: 'interested', memo: '',
        selfReportedSubmittedAt: null, createdAt: at, updatedAt: at,
      };
      db.saved.push(saved);
      // 공고 정보로 기본 체크리스트 생성 — 학생이 자유롭게 수정·삭제 가능
      const defaults = [
        '지원 자격 원문 확인',
        ...o.files.map((f) => `'${f.name}' 작성`),
        ...(o.destination ? [`제출처 확인: ${o.destination}`] : []),
      ];
      defaults.forEach((t, i) => db.checkItems.push({ id: uid('ci'), savedId: saved.id, text: t, completedAt: null, sortOrder: i }));
      return saved;
    }),
  );
}

export function updateSaved(savedId: string, patch: { status?: SavedStatus; memo?: string }) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const s = requireOwnSaved(db, user, savedId);
      const errors: Record<string, string> = {};
      if (patch.memo !== undefined) s.memo = text(errors, 'memo', '메모', patch.memo, 0, 1000);
      if (patch.status !== undefined) {
        if (!['interested', 'preparing', 'self_reported_submitted', 'closed'].includes(patch.status)) errors.status = '알 수 없는 상태입니다.';
        else {
          s.status = patch.status;
          s.selfReportedSubmittedAt = patch.status === 'self_reported_submitted' ? nowIso() : null;
        }
      }
      assertValid(errors);
      s.updatedAt = nowIso();
    }),
  );
}

export function unsaveOpportunity(savedId: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      requireOwnSaved(db, user, savedId);
      db.saved = db.saved.filter((s) => s.id !== savedId);
      db.checkItems = db.checkItems.filter((c) => c.savedId !== savedId);
    }),
  );
}

export function addCheckItem(savedId: string, input: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      requireOwnSaved(db, user, savedId);
      const errors: Record<string, string> = {};
      const t = text(errors, 'text', '항목', input, 1, 100);
      assertValid(errors);
      const items = db.checkItems.filter((c) => c.savedId === savedId);
      if (items.length >= 30) throw new ApiError('CONFLICT', '체크리스트는 30개까지 추가할 수 있습니다.');
      const item: CheckItem = { id: uid('ci'), savedId, text: t, completedAt: null, sortOrder: Math.max(-1, ...items.map((c) => c.sortOrder)) + 1 };
      db.checkItems.push(item);
    }),
  );
}

function requireOwnItem(db: Database, user: User, itemId: string) {
  const item = db.checkItems.find((c) => c.id === itemId);
  if (!item) notFound('체크리스트 항목');
  requireOwnSaved(db, user, item.savedId);
  return item;
}

export function updateCheckItem(itemId: string, patch: { text?: string; completed?: boolean }) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const item = requireOwnItem(db, user, itemId);
      const errors: Record<string, string> = {};
      if (patch.text !== undefined) item.text = text(errors, 'text', '항목', patch.text, 1, 100);
      assertValid(errors);
      if (patch.completed !== undefined) item.completedAt = patch.completed ? nowIso() : null;
    }),
  60);
}

export function deleteCheckItem(itemId: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      requireOwnItem(db, user, itemId);
      db.checkItems = db.checkItems.filter((c) => c.id !== itemId);
    }),
  60);
}
