'use strict';

/**
 * UI contract the harness drives. EXISTING entries are copied from labels already shipped in
 * apps/web (community/opportunities/auth/navigation). PROPOSED entries are open questions for
 * F/root (see docs/dev-prep/TASK_P0_BROWSER_E2E.md); failures cite the question ID in detail.
 */
const QUESTIONS = Object.freeze({
  LOGIN_ROUTE: 'Q-F1',
  SESSION_IDENTITY: 'Q-F2',
  RELOAD_SESSION: 'Q-F3',
  RECRUIT_DELETE: 'Q-F4',
  LOGOUT: 'Q-F5',
  SIGNED_OUT_GUARD: 'Q-F6',
  ROUTES: 'Q-F7',
  ME_SHAPE: 'Q-A1',
  CLOSED_DELETE: 'Q-A2',
  CROSS_ACCOUNT: 'Q-A3',
});

module.exports = Object.freeze({
  QUESTIONS,
  ROUTES: Object.freeze({
    login: '/app/login', // PROPOSED Q-F1
    community: '/app/community', // EXISTING navigation.ts
    recruitments: '/app/recruitments', // EXISTING navigation.ts
    opportunities: '/app/opportunities', // EXISTING navigation.ts
  }),
  NAV: Object.freeze({
    landmark: '캠퍼스 전체 메뉴',
    menuToggle: 'button[aria-controls="campus-navigation"]',
    community: '익명 커뮤니티',
    recruitments: '팀원 모집',
    opportunities: '장학 · 기회',
  }),
  // Optional in-page tabs (EXISTING community/index.tsx); clicked only when present.
  TABS: Object.freeze({ community: '익명 게시판', recruitments: '실명 모집' }),
  // List request each protected page issues on mount; used to tell "session restored" apart.
  LIST_API: Object.freeze({
    community: /^\/anonymous-posts$/,
    recruitments: /^\/recruitments$/,
    opportunities: /^\/me\/saved-opportunities$/,
  }),
  LOGIN: Object.freeze({
    studentId: '가상 학번', // EXISTING features/auth
    password: '비밀번호',
    submit: '가상 계정으로 로그인',
    logout: '로그아웃', // PROPOSED placement Q-F5
  }),
  ANON: Object.freeze({
    section: 'section[aria-labelledby="anon-heading"]',
    title: '제목',
    body: '본문',
    submit: '익명으로 등록 요청',
    edit: '수정',
    editTitle: '제목 수정',
    editBody: '본문 수정',
    save: '수정 요청',
    remove: '삭제',
    anonymousName: '익명',
  }),
  RECRUIT: Object.freeze({
    section: 'section[aria-labelledby="recruit-heading"]',
    title: '제목',
    field: '분야',
    roles: '모집 역할 (쉼표로 구분)',
    capacity: '총 인원 (모집자 포함)',
    deadline: '마감 일시',
    body: '설명',
    submit: '모집글 등록 요청',
    edit: '수정',
    editForm: '모집글 수정',
    save: '수정 요청',
    close: '모집 마감',
    remove: '삭제', // PROPOSED Q-F4
  }),
  OPP: Object.freeze({
    listSection: 'section[aria-labelledby="opp-list"]',
    savedSection: 'section[aria-labelledby="opp-saved"]',
    search: '검색어',
    openOnly: '마감 전만',
    save: '내 준비 목록에 추가',
    checkInput: '준비 항목',
    checkAdd: '추가',
    checkDone: (text) => `${text} 완료 여부`,
    checkRemove: '삭제',
    statusChange: /\(으\)로 변경$/,
    removeSaved: '목록에서 삭제',
  }),
});
