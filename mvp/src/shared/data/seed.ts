import type { Channel, Database, Department } from '../types';

// 시연 전용 가상 데이터 — 실제 학생 이름/학번/학교 시스템과 무관하다 (docs/05 §5).
export const DB_VERSION = 1;

const DAY = 24 * 60 * 60 * 1000;
const at = (offsetDays: number, hour = 9) => {
  const d = new Date(Date.now() + offsetDays * DAY);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
};

const departments: Department[] = [
  { id: 'dept-cs', name: '컴퓨터소프트웨어과' },
  { id: 'dept-design', name: '시각디자인과' },
];

/** 학과 전체 + 학년별 기본 채널 자동 프로비저닝 (docs/04 §4) */
function provisionChannels(): Channel[] {
  const channels: Channel[] = [];
  for (const d of departments) {
    channels.push({
      id: `ch-${d.id}-all`,
      departmentId: d.id,
      academicYear: null,
      kind: 'department',
      official: true,
      name: `${d.name} 전체`,
      description: '학과 구성원 전체 채널 · 공식 공지 카드가 자동으로 전달됩니다.',
      createdBy: null,
      createdAt: at(-30),
    });
    for (const year of [1, 2]) {
      channels.push({
        id: `ch-${d.id}-y${year}`,
        departmentId: d.id,
        academicYear: year,
        kind: 'year',
        official: true,
        name: `${d.name} ${year}학년`,
        description: `${year}학년 기본 채널 · 학년 대상 공지가 자동으로 전달됩니다.`,
        createdBy: null,
        createdAt: at(-30),
      });
    }
  }
  return channels;
}

export function createSeed(): Database {
  const channels = provisionChannels();
  channels.push({
    id: 'ch-free-algo',
    departmentId: 'dept-cs',
    academicYear: null,
    kind: 'free',
    official: false,
    name: '알고리즘 스터디',
    description: '코딩테스트 같이 준비해요 (학생 자유 채널)',
    createdBy: 'u-stu-b',
    createdAt: at(-5),
  });

  return {
    version: DB_VERSION,
    departments,
    users: [
      { id: 'u-stu-a', email: 'student1@demo.dit', name: '김하늘', role: 'student', departmentId: 'dept-cs', academicYear: 2 },
      { id: 'u-stu-b', email: 'student2@demo.dit', name: '이준서', role: 'student', departmentId: 'dept-cs', academicYear: 2 },
      { id: 'u-stu-c', email: 'student3@demo.dit', name: '박서윤', role: 'student', departmentId: 'dept-design', academicYear: 1 },
      { id: 'u-asst', email: 'assistant@demo.dit', name: '정민아', role: 'assistant', departmentId: 'dept-cs', academicYear: null },
      { id: 'u-admin', email: 'admin@demo.dit', name: '학사운영팀', role: 'admin', departmentId: 'dept-cs', academicYear: null },
    ],
    channels,
    messages: [
      {
        id: 'm-1', channelId: 'ch-dept-cs-y2', senderId: 'u-stu-b', kind: 'text',
        text: '이번 주 자료구조 과제 범위 어디까지인지 아시는 분?', referenceNoticeId: null, noticeRevision: null,
        clientNonce: 'seed-1', createdAt: at(-1, 13), deletedAt: null,
      },
      {
        id: 'm-2', channelId: 'ch-dept-cs-y2', senderId: 'u-stu-a', kind: 'text',
        text: '5장 연결리스트까지래요!', referenceNoticeId: null, noticeRevision: null,
        clientNonce: 'seed-2', createdAt: at(-1, 14), deletedAt: null,
      },
      {
        id: 'm-3', channelId: 'ch-dept-cs-y2', senderId: null, kind: 'notice_card',
        text: null, referenceNoticeId: 'n-1', noticeRevision: 1,
        clientNonce: 'delivery-n-1-1-ch-dept-cs-y2', createdAt: at(-1, 15), deletedAt: null,
      },
    ],
    notices: [
      {
        id: 'n-1', authorId: 'u-asst', audienceType: 'department_year', departmentId: 'dept-cs', academicYear: 2,
        category: '장학', title: '2학년 교내 근로장학생 추가 모집 안내',
        body: '학과 사무실 근로장학생을 추가 모집합니다.\n\n- 대상: 컴퓨터소프트웨어과 2학년\n- 근무: 주 10시간 (공강 시간 조율)\n- 신청: 학과 사무실 방문 또는 본 공지 문의\n\n※ 시연용 가상 공지입니다.',
        important: true, status: 'published', revision: 1, createdAt: at(-1, 15), updatedAt: at(-1, 15), deletedAt: null,
      },
      {
        id: 'n-2', authorId: 'u-admin', audienceType: 'all', departmentId: null, academicYear: null,
        category: '학사', title: '2학기 기말고사 기간 및 강의평가 안내',
        body: '기말고사 기간과 강의평가 일정 안내입니다. 강의평가 미참여 시 성적 조회가 제한될 수 있습니다.\n\n※ 시연용 가상 공지입니다.',
        important: false, status: 'published', revision: 1, createdAt: at(-3, 10), updatedAt: at(-3, 10), deletedAt: null,
      },
    ],
    noticeDeliveries: [
      { id: 'd-1', noticeId: 'n-1', revision: 1, channelId: 'ch-dept-cs-y2', eventType: 'published', createdAt: at(-1, 15) },
    ],
    anonPosts: [
      {
        id: 'p-1', authorId: 'u-stu-c', title: '학식 오늘 메뉴 괜찮나요?',
        body: '점심 뭐 먹을지 고민돼요. 오늘 학생식당 가보신 분 후기 부탁!', status: 'active',
        createdAt: at(0, 8), updatedAt: at(0, 8),
      },
      {
        id: 'p-2', authorId: 'u-stu-b', title: '도서관 열람실 콘센트 자리 팁',
        body: '3층 창가 쪽이 콘센트 자리 많아요. 시험기간엔 아침 일찍 가야 합니다.', status: 'active',
        createdAt: at(-2, 20), updatedAt: at(-2, 20),
      },
    ],
    anonComments: [
      { id: 'c-1', postId: 'p-1', authorId: 'u-stu-a', body: '돈까스 나왔는데 괜찮았어요', status: 'active', createdAt: at(0, 9) },
    ],
    recruitments: [
      {
        id: 'r-1', ownerId: 'u-stu-b', title: '캠퍼스 해커톤 같이 나가실 디자이너 구해요',
        body: '프론트/백엔드는 있고 UI 디자인 해주실 분을 찾습니다. 학과 무관 환영!',
        field: '해커톤', roles: 'UI/UX 디자이너 1명, 기획 1명', capacity: 4, deadline: at(7, 23),
        status: 'open', createdAt: at(-2, 11), updatedAt: at(-2, 11),
      },
    ],
    applications: [],
    opportunities: [
      {
        id: 'o-1', kind: '장학금', title: '지역인재 희망 장학금 (외부 재단)', organization: '가상 미래인재 장학재단',
        summary: '부산 지역 대학 재학생을 대상으로 한 외부 재단 장학금입니다. 지정 양식을 작성해 재단에 직접 제출해야 합니다.',
        eligibility: '직전 학기 12학점 이상 이수, 평점 3.0 이상 (원문 확인 필요)', target: '전 학과 재학생',
        startsAt: at(-3), deadline: at(5, 18), submissionMode: 'external_document_submission',
        destination: '재단 이메일 접수 (원문 공고 참고)', originalUrl: null,
        files: [{ name: '장학금 신청서 양식.hwp', url: null }, { name: '개인정보 수집 동의서.pdf', url: null }],
      },
      {
        id: 'o-2', kind: '근로', title: '학과 사무실 교내 근로장학생', organization: '컴퓨터소프트웨어과',
        summary: '학과 사무실 업무 보조 근로장학생 모집.', eligibility: '컴퓨터소프트웨어과 2학년', target: '컴퓨터소프트웨어과 2학년',
        startsAt: at(-1), deadline: at(3, 17), submissionMode: 'info_only', destination: '학과 사무실 방문', originalUrl: null,
        files: [],
      },
      {
        id: 'o-3', kind: '공모전', title: '부산 청년 아이디어 공모전', organization: '가상 부산청년센터',
        summary: '지역 문제 해결 아이디어를 제안하는 공모전. 2~4인 팀 참가 가능.', eligibility: '부산 소재 대학생', target: '전 학과',
        startsAt: at(-7), deadline: at(14, 18), submissionMode: 'external_link', destination: '공모전 홈페이지 온라인 접수',
        originalUrl: null, files: [{ name: '참가 신청서.docx', url: null }],
      },
      {
        id: 'o-4', kind: '취업', title: 'IT 기업 현장실습 설명회', organization: '가상 현장실습지원센터',
        summary: '겨울방학 현장실습 참여 기업 설명회.', eligibility: '2학년 이상', target: '전 학과',
        startsAt: at(-2), deadline: at(10, 15), submissionMode: 'info_only', destination: '본관 대강당 현장 참석', originalUrl: null,
        files: [],
      },
    ],
    saved: [],
    checkItems: [],
    courses: [
      { id: 'cr-1', name: '자료구조', professor: '최도현', room: '정보관 401', departmentId: 'dept-cs', slots: [{ weekday: 1, start: '09:00', end: '11:50' }, { weekday: 3, start: '13:00', end: '14:50' }] },
      { id: 'cr-2', name: '웹프로그래밍', professor: '한지우', room: '정보관 305', departmentId: 'dept-cs', slots: [{ weekday: 2, start: '10:00', end: '12:50' }, { weekday: 4, start: '14:00', end: '16:50' }] },
      { id: 'cr-3', name: '데이터베이스', professor: '최도현', room: '정보관 402', departmentId: 'dept-cs', slots: [{ weekday: 4, start: '09:00', end: '11:50' }, { weekday: 5, start: '10:00', end: '11:50' }] },
      { id: 'cr-4', name: '타이포그래피', professor: '윤가은', room: '예술관 201', departmentId: 'dept-design', slots: [{ weekday: 1, start: '13:00', end: '15:50' }, { weekday: 4, start: '10:00', end: '12:50' }] },
      { id: 'cr-5', name: '디자인 드로잉', professor: '서민호', room: '예술관 105', departmentId: 'dept-design', slots: [{ weekday: 2, start: '09:00', end: '11:50' }, { weekday: 5, start: '13:00', end: '15:50' }] },
    ],
    enrollments: [
      { studentId: 'u-stu-a', courseId: 'cr-1' }, { studentId: 'u-stu-a', courseId: 'cr-2' }, { studentId: 'u-stu-a', courseId: 'cr-3' },
      { studentId: 'u-stu-b', courseId: 'cr-1' }, { studentId: 'u-stu-b', courseId: 'cr-3' },
      { studentId: 'u-stu-c', courseId: 'cr-4' }, { studentId: 'u-stu-c', courseId: 'cr-5' },
    ],
  };
}
