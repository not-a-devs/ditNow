// Fixed display text for server rule codes. Wording never claims AI generation or eligibility.
import type { CautionCode, Freshness, ReasonCode, StepCode, Window } from './types';

export const REASON_LABEL: Record<ReasonCode, string> = {
  SCHOOL_WIDE: '전교 대상 공고',
  DEPARTMENT_MATCH: '현재 소속 학과가 공고 대상 학과에 포함',
  GRADE_MATCH: '현재 학년이 공고 대상 학년에 포함',
  KIND_INTEREST: '선택한 관심 분류',
  KEYWORD_INTEREST: '입력한 관심 키워드 포함',
  DEADLINE_SOON: '마감 7일 이내',
};

export const WINDOW_LABEL: Record<Window, string> = {
  UPCOMING: '접수 시작 전',
  OPEN: '접수 중',
  CLOSED: '마감',
  NO_DEADLINE: '마감일 정보 없음',
};

export const FRESHNESS_LABEL: Record<Freshness, string> = {
  CURRENT: '최근 30일 내 원문 확인',
  STALE: '원문 확인 30일 경과 — 다시 확인 필요',
  UNVERIFIED: '원문 확인 일시 없음',
};

export const CAUTION_LABEL: Record<CautionCode, string> = {
  NOT_ELIGIBILITY_DECISION: '이 정보는 지원 자격 판정이 아닙니다. 자격은 원문 공고 기준입니다.',
  EXTERNAL_SUBMISSION: '이 플랫폼은 지원서를 받거나 접수를 확인하지 않습니다.',
  DEMO_SOURCE: 'DEMO 가상 공고입니다.',
  NEEDS_VERIFICATION: '원문 링크 또는 확인 일시가 없어 원문 확인이 필요합니다.',
  STALE_SOURCE: '원문을 확인한 지 30일이 지났습니다.',
  UNVERIFIED_SOURCE: '원문을 확인한 일시 정보가 없습니다.',
  DEADLINE_PASSED: '마감일이 지났습니다.',
  NOT_YET_OPEN: '아직 접수 시작 전입니다.',
  OUT_OF_SCOPE: '현재 소속 학과·학년이 공고 대상 범위에 포함되지 않습니다.',
  NO_APPLICATION_PROCEDURE: '안내용 공고로 신청 절차 정보가 없습니다.',
};

export const STEP_LABEL: Record<StepCode, string> = {
  CHECK_ORIGINAL: '원문 공고 확인',
  DOWNLOAD_FORM: '지정 양식 내려받기',
  SUBMIT_TO_DESTINATION: '주관 기관 제출처에 직접 제출',
  APPLY_VIA_LINK: '주관 기관 외부 페이지에서 신청',
  SELF_RECORD: '제출 후 내 준비 상태에 직접 기록(기관 확인 아님)',
};

export const STEP_MISSING: Record<StepCode, string> = {
  CHECK_ORIGINAL: '원문 링크 정보 없음',
  DOWNLOAD_FORM: '양식 파일 정보 없음 — 원문 공고를 확인하세요',
  SUBMIT_TO_DESTINATION: '제출처 정보 없음 — 원문 공고를 확인하세요',
  APPLY_VIA_LINK: '신청 링크 정보 없음',
  SELF_RECORD: '',
};
