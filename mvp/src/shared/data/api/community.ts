import type {
  AnonymousCommentPublic,
  AnonymousPostPrivate,
  AnonymousPostPublic,
  Database,
  Recruitment,
  RecruitmentApplication,
  User,
} from '../../types';
import { readDb, transact, uid, nowIso } from '../store';
import { ApiError, assertValid, departmentName, latency, notFound, requireRole, requireUser, text } from './core';

// ───────────────────────── 익명 자유게시판 (FR-COM-001~002) ─────────────────────────
// 공개 응답은 projection만 반환한다: author_id/실명/학과 등 역추적 값 없음 (NFR-PRIV-001).
// 커뮤니티 참여는 학생 역할만 (OPEN-005 안전 처리).

function toPublicPost(db: Database, user: User, p: AnonymousPostPrivate): AnonymousPostPublic {
  return {
    id: p.id,
    title: p.title,
    body: p.body,
    createdAt: p.createdAt,
    updatedAt: p.updatedAt,
    commentCount: db.anonComments.filter((c) => c.postId === p.id && c.status === 'active').length,
    isMine: p.authorId === user.id,
  };
}

function getActivePost(db: Database, id: string) {
  const post = db.anonPosts.find((p) => p.id === id && p.status === 'active');
  if (!post) notFound('게시글');
  return post;
}

export function listAnonPosts(opts: { query?: string; limit?: number; offset?: number } = {}) {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    requireRole(user, ['student']);
    const q = opts.query?.trim().toLowerCase() ?? '';
    const limit = opts.limit ?? 10;
    const offset = opts.offset ?? 0;
    const rows = db.anonPosts
      .filter((p) => p.status === 'active')
      .filter((p) => !q || p.title.toLowerCase().includes(q) || p.body.toLowerCase().includes(q))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    return {
      items: rows.slice(offset, offset + limit).map((p) => toPublicPost(db, user, p)),
      total: rows.length,
    };
  });
}

export function getAnonPost(id: string) {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    requireRole(user, ['student']);
    const post = getActivePost(db, id);
    // 글 안에서만 유효한 익명 번호: 첫 댓글 순서대로 익명1, 익명2 ... (글쓴이는 '글쓴이')
    const aliases = new Map<string, string>();
    const comments: AnonymousCommentPublic[] = db.anonComments
      .filter((c) => c.postId === id && c.status === 'active')
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .map((c) => {
        if (!aliases.has(c.authorId)) {
          aliases.set(c.authorId, c.authorId === post.authorId ? '글쓴이' : `익명${[...aliases.values()].filter((v) => v !== '글쓴이').length + 1}`);
        }
        return { id: c.id, body: c.body, createdAt: c.createdAt, alias: aliases.get(c.authorId)!, isMine: c.authorId === user.id };
      });
    return { post: toPublicPost(db, user, post), comments };
  });
}

function validatePost(input: { title: string; body: string }) {
  const errors: Record<string, string> = {};
  const title = text(errors, 'title', '제목', input.title, 2, 120);
  const body = text(errors, 'body', '본문', input.body, 1, 5000);
  assertValid(errors);
  return { title, body };
}

export function createAnonPost(input: { title: string; body: string }) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      requireRole(user, ['student']);
      const v = validatePost(input);
      const at = nowIso();
      const post: AnonymousPostPrivate = { id: uid('p'), authorId: user.id, ...v, status: 'active', createdAt: at, updatedAt: at };
      db.anonPosts.push(post);
      return { id: post.id };
    }),
  );
}

function requireOwnPost(db: Database, user: User, id: string) {
  const post = getActivePost(db, id);
  // 소유권은 서버 내부 매핑으로만 확인 — 응답에 신원 노출 없음
  if (post.authorId !== user.id) throw new ApiError('FORBIDDEN', '작성자만 수정·삭제할 수 있습니다.');
  return post;
}

export function updateAnonPost(id: string, input: { title: string; body: string }) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const post = requireOwnPost(db, user, id);
      Object.assign(post, validatePost(input), { updatedAt: nowIso() });
      return { id };
    }),
  );
}

export function deleteAnonPost(id: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const post = requireOwnPost(db, user, id);
      post.status = 'deleted';
      post.updatedAt = nowIso();
    }),
  );
}

export function addAnonComment(postId: string, body: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      requireRole(user, ['student']);
      getActivePost(db, postId);
      const errors: Record<string, string> = {};
      const v = text(errors, 'body', '댓글', body, 1, 1000);
      assertValid(errors);
      db.anonComments.push({ id: uid('c'), postId, authorId: user.id, body: v, status: 'active', createdAt: nowIso() });
    }),
  );
}

export function deleteAnonComment(commentId: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const c = db.anonComments.find((x) => x.id === commentId && x.status === 'active');
      if (!c) notFound('댓글');
      if (c.authorId !== user.id) throw new ApiError('FORBIDDEN', '작성자만 삭제할 수 있습니다.');
      c.status = 'deleted';
    }),
  );
}

// ───────────────────────── 실명 팀원 모집 (FR-COM-004~005) ─────────────────────────
// 작성자는 공개 실명 활동 프로필(이름·학과)만 표시. 학교 공식 실명 인증과 무관.

export interface RecruitmentView extends Recruitment {
  ownerName: string;
  ownerDepartment: string;
  acceptedCount: number;
  isOwner: boolean;
  isExpired: boolean;
  myApplication: RecruitmentApplication | null;
}

export interface ApplicationView extends RecruitmentApplication {
  applicantName: string;
  applicantDepartment: string;
}

function toRecruitmentView(db: Database, user: User, r: Recruitment): RecruitmentView {
  const owner = db.users.find((u) => u.id === r.ownerId);
  return {
    ...r,
    ownerName: owner?.name ?? '알 수 없음',
    ownerDepartment: departmentName(db, owner?.departmentId ?? null),
    acceptedCount: db.applications.filter((a) => a.recruitmentId === r.id && a.status === 'accepted').length,
    isOwner: r.ownerId === user.id,
    isExpired: new Date(r.deadline).getTime() < Date.now(),
    myApplication: db.applications.find((a) => a.recruitmentId === r.id && a.applicantId === user.id) ?? null,
  };
}

export function listRecruitments(opts: { onlyOpen?: boolean } = {}) {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    requireRole(user, ['student']);
    return db.recruitments
      .filter((r) => r.status !== 'cancelled')
      .filter((r) => !opts.onlyOpen || r.status === 'open')
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .map((r) => toRecruitmentView(db, user, r));
  });
}

export function getRecruitment(id: string) {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    requireRole(user, ['student']);
    const r = db.recruitments.find((x) => x.id === id && x.status !== 'cancelled');
    if (!r) notFound('모집글');
    const view = toRecruitmentView(db, user, r);
    // 지원자 목록은 모집자 본인에게만
    const applications: ApplicationView[] = view.isOwner
      ? db.applications
          .filter((a) => a.recruitmentId === id && a.status !== 'withdrawn')
          .map((a) => {
            const u = db.users.find((x) => x.id === a.applicantId);
            return { ...a, applicantName: u?.name ?? '알 수 없음', applicantDepartment: departmentName(db, u?.departmentId ?? null) };
          })
      : [];
    return { recruitment: view, applications };
  });
}

export interface RecruitmentInput {
  title: string;
  body: string;
  field: string;
  roles: string;
  capacity: number;
  deadline: string;
}

function validateRecruitment(input: RecruitmentInput) {
  const errors: Record<string, string> = {};
  const title = text(errors, 'title', '제목', input.title, 2, 120);
  const body = text(errors, 'body', '설명', input.body, 1, 5000);
  const field = text(errors, 'field', '분야', input.field, 1, 30);
  const roles = text(errors, 'roles', '모집 역할', input.roles, 1, 200);
  const capacity = Number(input.capacity);
  if (!Number.isInteger(capacity) || capacity < 2 || capacity > 20) errors.capacity = '팀 인원은 본인 포함 2~20명입니다.';
  const deadline = new Date(input.deadline);
  if (Number.isNaN(deadline.getTime())) errors.deadline = '마감일을 입력해 주세요.';
  else if (deadline.getTime() < Date.now()) errors.deadline = '마감일은 현재 이후여야 합니다.';
  assertValid(errors);
  return { title, body, field, roles, capacity, deadline: deadline.toISOString() };
}

export function createRecruitment(input: RecruitmentInput) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      requireRole(user, ['student']);
      const v = validateRecruitment(input);
      const at = nowIso();
      const r: Recruitment = { id: uid('r'), ownerId: user.id, ...v, status: 'open', createdAt: at, updatedAt: at };
      db.recruitments.push(r);
      return { id: r.id };
    }),
  );
}

function requireOwnRecruitment(db: Database, user: User, id: string) {
  const r = db.recruitments.find((x) => x.id === id && x.status !== 'cancelled');
  if (!r) notFound('모집글');
  if (r.ownerId !== user.id) throw new ApiError('FORBIDDEN', '모집글 작성자만 관리할 수 있습니다.');
  return r;
}

export function updateRecruitment(id: string, input: RecruitmentInput) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const r = requireOwnRecruitment(db, user, id);
      const v = validateRecruitment(input);
      const accepted = db.applications.filter((a) => a.recruitmentId === id && a.status === 'accepted').length;
      if (v.capacity - 1 < accepted) {
        throw new ApiError('CONFLICT', '이미 승인한 인원보다 적게 줄일 수 없습니다.', { capacity: `이미 ${accepted}명 승인됨` });
      }
      Object.assign(r, v, { updatedAt: nowIso() });
      return { id };
    }),
  );
}

export function setRecruitmentStatus(id: string, status: 'open' | 'closed') {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const r = requireOwnRecruitment(db, user, id);
      r.status = status;
      r.updatedAt = nowIso();
    }),
  );
}

export function deleteRecruitment(id: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const r = requireOwnRecruitment(db, user, id);
      r.status = 'cancelled';
      r.updatedAt = nowIso();
    }),
  );
}

export function applyRecruitment(id: string, message: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      requireRole(user, ['student']);
      const r = db.recruitments.find((x) => x.id === id && x.status !== 'cancelled');
      if (!r) notFound('모집글');
      if (r.ownerId === user.id) throw new ApiError('CONFLICT', '본인 모집글에는 지원할 수 없습니다.');
      if (r.status !== 'open' || new Date(r.deadline).getTime() < Date.now()) throw new ApiError('CONFLICT', '모집이 마감되었습니다.');
      const errors: Record<string, string> = {};
      const msg = text(errors, 'message', '지원 메시지', message, 1, 500);
      assertValid(errors);
      const existing = db.applications.find((a) => a.recruitmentId === id && a.applicantId === user.id);
      if (existing && existing.status !== 'withdrawn') throw new ApiError('CONFLICT', '이미 지원한 모집글입니다.');
      if (existing) Object.assign(existing, { status: 'pending', message: msg, createdAt: nowIso() });
      else db.applications.push({ id: uid('a'), recruitmentId: id, applicantId: user.id, message: msg, status: 'pending', createdAt: nowIso() });
    }),
  );
}

export function withdrawApplication(applicationId: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const a = db.applications.find((x) => x.id === applicationId);
      if (!a) notFound('지원 내역');
      if (a.applicantId !== user.id) throw new ApiError('FORBIDDEN', '본인 지원만 철회할 수 있습니다.');
      if (a.status !== 'pending') throw new ApiError('CONFLICT', '대기 중인 지원만 철회할 수 있습니다.');
      a.status = 'withdrawn';
    }),
  );
}

/** 정원 검사를 같은 트랜잭션 안에서 수행 — 화면 카운트만 믿지 않는다 (docs/05 불변식 4) */
export function decideApplication(applicationId: string, decision: 'accepted' | 'rejected') {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const a = db.applications.find((x) => x.id === applicationId);
      if (!a) notFound('지원 내역');
      const r = requireOwnRecruitment(db, user, a.recruitmentId);
      if (a.status !== 'pending') throw new ApiError('CONFLICT', '이미 처리된 지원입니다.');
      if (decision === 'accepted') {
        const accepted = db.applications.filter((x) => x.recruitmentId === r.id && x.status === 'accepted').length;
        if (accepted >= r.capacity - 1) throw new ApiError('CONFLICT', '정원이 가득 찼습니다.');
        a.status = 'accepted';
        if (accepted + 1 >= r.capacity - 1) r.status = 'closed';
      } else {
        a.status = 'rejected';
      }
      r.updatedAt = nowIso();
    }),
  );
}
