export const navigation = [
  { id: 'home', label: '캠퍼스 홈', path: '/app', category: '나의 캠퍼스', description: '수업과 소식, 기회를 한눈에' },
  { id: 'academic', label: '학사 · 시간표', path: '/app/academic', category: '나의 캠퍼스', description: '학사 일정부터 나의 수업까지' },
  { id: 'classrooms', label: '내 강의실', path: '/app/classrooms', category: '나의 캠퍼스', description: '자료, 과제, 질문이 모이는 곳' },
  { id: 'department', label: '우리 학과', path: '/app/department', category: '함께하는 대학', description: '학과 전체 · 학년별 소통' },
  { id: 'community', label: '익명 커뮤니티', path: '/app/community', category: '함께하는 대학', description: '이름 대신 생각으로 만나는 공간' },
  { id: 'recruitments', label: '팀원 모집', path: '/app/recruitments', category: '함께하는 대학', description: '실명으로 시작하는 새로운 협업' },
  { id: 'opportunities', label: '장학 · 기회', path: '/app/opportunities', category: '더 넓은 캠퍼스', description: '장학금, 공모전, 취업의 다음 기회' },
  { id: 'support', label: '학생 지원', path: '/app/support', category: '더 넓은 캠퍼스', description: '도서관, 생활, 상담과 지원' },
  { id: 'information', label: '대학 · 학과 안내', path: '/app/information', category: '더 넓은 캠퍼스', description: '공개 자료를 바탕으로 대학과 학과 탐색' },
  { id: 'ai', label: 'AI 도우미', path: '/app/ai', category: '더 넓은 캠퍼스', description: '궁금한 캠퍼스 생활을 함께 탐색' },
] as const;
export type SectionId = typeof navigation[number]['id'];
