import type { Briefing, Course, Database, User } from '../../types';
import { readDb } from '../store';
import { latency, requireUser } from './core';

export interface ClassSlotView {
  courseId: string;
  name: string;
  professor: string;
  room: string;
  weekday: number;
  start: string;
  end: string;
}

function myCourses(db: Database, user: User): Course[] {
  const ids = new Set(db.enrollments.filter((e) => e.studentId === user.id).map((e) => e.courseId));
  return db.courses.filter((c) => ids.has(c.id));
}

function slotsOf(courses: Course[]): ClassSlotView[] {
  return courses
    .flatMap((c) => c.slots.map((s) => ({ courseId: c.id, name: c.name, professor: c.professor, room: c.room, ...s })))
    .sort((a, b) => a.weekday - b.weekday || a.start.localeCompare(b.start));
}

export function getTimetable() {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    return slotsOf(myCourses(db, user));
  });
}

const DAY = 24 * 60 * 60 * 1000;
const daysLeft = (iso: string) => Math.ceil((new Date(iso).getTime() - Date.now()) / DAY);

/**
 * 오늘의 브리핑 (FR-AI-001 출력 스키마와 동일).
 * 사전 MVP에서는 AI 모델을 호출하지 않고 서버 규칙으로만 생성한다 — generatedBy: 'rule'.
 * 이후 AI 연결 시에도 이 규칙 결과가 실패 대체(fallback)로 남는다.
 */
export function getBriefing() {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    const actions: Briefing['actions'] = [];
    const cautions: string[] = [];

    const today = new Date().getDay();
    const todays = slotsOf(myCourses(db, user)).filter((s) => s.weekday === today);
    todays.forEach((s) =>
      actions.push({ title: `${s.start} ${s.name}`, reason: `오늘 ${s.room}에서 수업이 있습니다.`, source_type: 'course', source_id: s.courseId }),
    );

    const mySaved = db.saved.filter((s) => s.userId === user.id && s.status !== 'self_reported_submitted' && s.status !== 'closed');
    for (const s of mySaved) {
      const o = db.opportunities.find((x) => x.id === s.opportunityId);
      if (!o) continue;
      const left = daysLeft(o.deadline);
      if (left < 0) continue;
      const items = db.checkItems.filter((c) => c.savedId === s.id);
      const remaining = items.filter((c) => !c.completedAt).length;
      if (left <= 7) {
        actions.push({
          title: `${o.title} 준비`,
          reason: `마감 D-${left}${remaining ? ` · 체크리스트 ${remaining}개 남음` : ' · 체크리스트 완료'}`,
          source_type: 'opportunity',
          source_id: o.id,
        });
      }
    }

    const recent = db.notices.filter(
      (n) =>
        !n.deletedAt &&
        n.status === 'published' &&
        n.important &&
        Date.now() - new Date(n.updatedAt).getTime() < 7 * DAY &&
        (n.audienceType === 'all' ||
          (n.departmentId === user.departmentId &&
            (n.audienceType === 'department' || user.role !== 'student' || n.academicYear === user.academicYear))),
    );
    recent.forEach((n) => actions.push({ title: n.title, reason: '최근 7일 내 중요 공식 공지입니다.', source_type: 'notice', source_id: n.id }));

    const myRecruitPending = db.recruitments
      .filter((r) => r.ownerId === user.id && r.status === 'open')
      .map((r) => ({ r, n: db.applications.filter((a) => a.recruitmentId === r.id && a.status === 'pending').length }))
      .filter((x) => x.n > 0);
    myRecruitPending.forEach(({ r, n }) =>
      actions.push({ title: `${r.title} 지원자 확인`, reason: `대기 중인 지원 ${n}건`, source_type: 'recruitment', source_id: r.id }),
    );

    cautions.push('장학금·공모전 제출 여부는 직접 기록한 내용이며, 기관 접수 확인이 아닙니다.');
    const summary =
      actions.length === 0
        ? '오늘 바로 확인할 일정이나 마감이 없습니다.'
        : `오늘 수업 ${todays.length}개, 확인할 마감·공지 ${actions.length - todays.length}건이 있습니다.`;
    const briefing: Briefing = { summary, actions: actions.slice(0, 6), cautions, generatedBy: 'rule' };
    return briefing;
  });
}

export function getMySavedSummary() {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    return db.saved
      .filter((s) => s.userId === user.id)
      .map((s) => {
        const o = db.opportunities.find((x) => x.id === s.opportunityId)!;
        const items = db.checkItems.filter((c) => c.savedId === s.id);
        return { saved: s, opportunity: o, done: items.filter((c) => c.completedAt).length, total: items.length };
      })
      .filter((x) => x.opportunity)
      .sort((a, b) => a.opportunity.deadline.localeCompare(b.opportunity.deadline));
  });
}
