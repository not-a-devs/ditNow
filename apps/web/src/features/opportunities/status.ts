// Display rules for FR-OPP-004. Server remains the authority on transitions (409 otherwise).
import type { OpportunityKind, PreparationStatus, SubmissionMode } from './types';

export const KIND_LABEL: Record<OpportunityKind, string> = {
  scholarship: '장학금',
  work_study: '근로',
  career: '취업',
  contest: '공모전',
  event: '행사',
};

// NFR-DATA-002: never phrase self_reported_submitted as an accepted/confirmed application.
export const STATUS_LABEL: Record<PreparationStatus, string> = {
  interested: '관심',
  preparing: '준비 중',
  self_reported_submitted: '제출했다고 직접 기록함',
  closed: '마감·종료',
};

export const SUBMISSION_GUIDE: Record<SubmissionMode, string> = {
  external_document_submission:
    '지정 양식을 내려받아 주관 기관에 직접 제출하세요. 이 플랫폼은 지원서를 받거나 접수를 확인하지 않습니다.',
  external_link: '주관 기관의 외부 페이지에서 직접 신청하세요. 이 플랫폼은 접수 결과를 알 수 없습니다.',
  info_only: '안내용 공고입니다. 제출 절차가 없습니다.',
};

export const SELF_REPORT_NOTICE =
  '이 기록은 본인이 남기는 메모일 뿐 기관의 접수·선정 확인이 아닙니다.';

const ALLOWED: Record<PreparationStatus, PreparationStatus[]> = {
  interested: ['preparing', 'closed'],
  preparing: ['interested', 'self_reported_submitted', 'closed'],
  self_reported_submitted: ['preparing', 'closed'],
  closed: [],
};

export function nextStatuses(
  current: PreparationStatus,
  mode: SubmissionMode | undefined,
): PreparationStatus[] {
  return ALLOWED[current].filter(
    (status) => !(status === 'self_reported_submitted' && (mode === 'info_only' || !mode)),
  );
}

export function formatDateTime(value: string | null): string {
  if (!value) return '기한 정보 없음';
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Seoul',
  }).format(new Date(value));
}
