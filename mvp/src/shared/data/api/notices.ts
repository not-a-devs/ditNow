import type { AudienceType, Database, Notice, NoticeCategory, User } from '../../types';
import { readDb, transact, uid, nowIso } from '../store';
import { ApiError, assertValid, departmentName, isStaff, latency, notFound, requireRole, requireUser, roleLabel, text } from './core';

export const NOTICE_CATEGORIES: NoticeCategory[] = ['학사', '장학', '행사', '취업', '일반'];

export function audienceLabel(db: Database, n: Pick<Notice, 'audienceType' | 'departmentId' | 'academicYear'>) {
  if (n.audienceType === 'all') return '학교 전체';
  const dept = departmentName(db, n.departmentId);
  return n.audienceType === 'department' ? `${dept} 전체` : `${dept} ${n.academicYear}학년`;
}

/** 학생이 이 공지의 대상인지 (서버 권한 필터) */
function isAudience(user: User, n: Notice) {
  if (user.role === 'admin') return true;
  if (n.audienceType === 'all') return true;
  if (n.departmentId !== user.departmentId) return false;
  if (n.audienceType === 'department_year' && user.role === 'student') return n.academicYear === user.academicYear;
  return true;
}

/** 작성/수정 가능한 공지인지 — 조교·교수는 배정 학과, 관리자는 전체 */
function canManage(user: User, n: Pick<Notice, 'audienceType' | 'departmentId'>) {
  if (user.role === 'admin') return true;
  if (user.role !== 'assistant' && user.role !== 'professor') return false;
  return n.audienceType !== 'all' && n.departmentId === user.departmentId;
}

/**
 * 공지 → 대상 채널 공식 카드 배포 (FR-NOT-002, docs/06 §5).
 * (notice_id, revision, channel_id, event_type) 고유키로 재시도해도 카드는 1개만 생긴다.
 * 학교 전체 공지는 학과 채팅에 일괄 복제하지 않는다 (DFLT-004).
 */
function deliver(db: Database, notice: Notice, eventType: 'published' | 'revised') {
  if (notice.audienceType === 'all') return 0;
  const targets = db.channels.filter((c) => {
    if (c.departmentId !== notice.departmentId) return false;
    if (notice.audienceType === 'department') return c.kind === 'department';
    return c.kind === 'year' && c.academicYear === notice.academicYear;
  });
  let created = 0;
  for (const ch of targets) {
    const exists = db.noticeDeliveries.some(
      (d) => d.noticeId === notice.id && d.revision === notice.revision && d.channelId === ch.id && d.eventType === eventType,
    );
    if (exists) continue;
    const at = nowIso();
    db.noticeDeliveries.push({ id: uid('d'), noticeId: notice.id, revision: notice.revision, channelId: ch.id, eventType, createdAt: at });
    db.messages.push({
      id: uid('m'),
      channelId: ch.id,
      senderId: null,
      kind: 'notice_card',
      text: null, // 원문 전체 복사 금지 — 참조만 저장
      referenceNoticeId: notice.id,
      noticeRevision: notice.revision,
      clientNonce: `delivery-${notice.id}-${notice.revision}-${ch.id}-${eventType}`,
      createdAt: at,
      deletedAt: null,
    });
    created++;
  }
  return created;
}

export interface NoticeView extends Notice {
  audience: string;
  authorName: string;
  authorRole: string;
  canManage: boolean;
  deliveredChannels: string[];
}

function toView(db: Database, user: User, n: Notice): NoticeView {
  const author = db.users.find((u) => u.id === n.authorId);
  const channelIds = new Set(db.noticeDeliveries.filter((d) => d.noticeId === n.id).map((d) => d.channelId));
  return {
    ...n,
    audience: audienceLabel(db, n),
    authorName: author?.name ?? '알 수 없음',
    authorRole: author ? roleLabel[author.role] : '',
    canManage: canManage(user, n),
    deliveredChannels: db.channels.filter((c) => channelIds.has(c.id)).map((c) => c.name),
  };
}

export function listNoticesForMe(limit = 20) {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    return db.notices
      .filter((n) => !n.deletedAt && n.status === 'published' && isAudience(user, n))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .slice(0, limit)
      .map((n) => toView(db, user, n));
  });
}

export function getNotice(id: string) {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    const n = db.notices.find((x) => x.id === id);
    if (!n) notFound('공지');
    if (!isAudience(user, n) && !canManage(user, n)) throw new ApiError('FORBIDDEN', '이 공지의 대상이 아닙니다.');
    return toView(db, user, n);
  });
}

export function listManagedNotices() {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    if (!isStaff(user)) throw new ApiError('FORBIDDEN', '교직원만 공지를 관리할 수 있습니다.');
    return db.notices
      .filter((n) => !n.deletedAt && canManage(user, n))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .map((n) => toView(db, user, n));
  });
}

export interface NoticeInput {
  audienceType: AudienceType;
  academicYear: number | null;
  category: NoticeCategory;
  title: string;
  body: string;
  important: boolean;
}

function validate(db: Database, user: User, input: NoticeInput) {
  const errors: Record<string, string> = {};
  const title = text(errors, 'title', '제목', input.title, 1, 120);
  const body = text(errors, 'body', '내용', input.body, 1, 10000);
  if (!NOTICE_CATEGORIES.includes(input.category)) errors.category = '카테고리를 선택해 주세요.';
  if (!['all', 'department', 'department_year'].includes(input.audienceType)) errors.audienceType = '게시 대상을 선택해 주세요.';
  if (input.audienceType === 'all' && user.role !== 'admin') errors.audienceType = '학교 전체 공지는 학교 담당자만 게시할 수 있습니다.';
  if (input.audienceType === 'department_year' && ![1, 2].includes(input.academicYear ?? 0)) errors.academicYear = '학년을 선택해 주세요.';
  assertValid(errors);
  const departmentId = input.audienceType === 'all' ? null : user.departmentId;
  if (departmentId && !db.departments.some((d) => d.id === departmentId)) throw new ApiError('FORBIDDEN', '배정된 학과가 없습니다.');
  return {
    title,
    body,
    category: input.category,
    audienceType: input.audienceType,
    departmentId,
    academicYear: input.audienceType === 'department_year' ? input.academicYear : null,
    important: !!input.important,
  };
}

export function createNotice(input: NoticeInput) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      requireRole(user, ['assistant', 'professor', 'admin']);
      const v = validate(db, user, input);
      const at = nowIso();
      const notice: Notice = { id: uid('n'), authorId: user.id, ...v, status: 'published', revision: 1, createdAt: at, updatedAt: at, deletedAt: null };
      db.notices.push(notice);
      const delivered = deliver(db, notice, 'published');
      return { notice, delivered };
    }),
  );
}

/** 수정 시 revision++. 기존 카드는 같은 원본의 최신판을 가리킨다. renotify면 수정 안내 카드 1회 */
export function updateNotice(id: string, input: NoticeInput, renotify: boolean) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const notice = db.notices.find((n) => n.id === id && !n.deletedAt);
      if (!notice) notFound('공지');
      if (!canManage(user, notice)) throw new ApiError('FORBIDDEN', '본인 학과 공지만 수정할 수 있습니다.');
      const v = validate(db, user, input);
      if (v.audienceType !== notice.audienceType || v.academicYear !== notice.academicYear) {
        throw new ApiError('CONFLICT', '게시 대상은 수정할 수 없습니다. 새 공지로 등록해 주세요.', { audienceType: '게시 후 대상 변경 불가' });
      }
      Object.assign(notice, v, { revision: notice.revision + 1, updatedAt: nowIso() });
      const delivered = renotify ? deliver(db, notice, 'revised') : 0;
      return { notice, delivered };
    }),
  );
}

export function setNoticeArchived(id: string, archived: boolean) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const notice = db.notices.find((n) => n.id === id && !n.deletedAt);
      if (!notice) notFound('공지');
      if (!canManage(user, notice)) throw new ApiError('FORBIDDEN', '본인 학과 공지만 관리할 수 있습니다.');
      notice.status = archived ? 'archived' : 'published';
      notice.updatedAt = nowIso();
    }),
  );
}

/** 소프트 삭제 — 기존 채팅 카드는 '삭제된 공지'로 표시된다 */
export function deleteNotice(id: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const notice = db.notices.find((n) => n.id === id && !n.deletedAt);
      if (!notice) notFound('공지');
      if (!canManage(user, notice)) throw new ApiError('FORBIDDEN', '본인 학과 공지만 삭제할 수 있습니다.');
      notice.deletedAt = nowIso();
    }),
  );
}
