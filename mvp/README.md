# DIT NOW — 사전 MVP (프론트엔드 프로토타입)

`docs/` 명세(특히 `09_RELEASE_SCOPE.md`의 P0 흐름)를 바탕으로 만든 **사전 MVP**입니다.
서버 DB 없이 브라우저 `localStorage`에 저장하는 **시연용 프로토타입**이며, 실제 학교 시스템·SSO와 연결되어 있지 않습니다.

> ⚠️ 해커톤 심사 기준(서버 DB CRUD, RLS, 배포)을 충족하려면 `src/shared/data/` 계층을 Supabase로 교체해야 합니다. 아래 "다음 단계" 참고.

## 실행

```bash
cd mvp
npm install
npm run dev        # http://localhost:5173
npm run build      # 타입체크 + 프로덕션 빌드
```

## 시연 계정 (비밀번호 공통 `dit1234`)

| 계정 | 역할 | 소속 |
|---|---|---|
| student1@demo.dit | 학생 김하늘 | 컴퓨터소프트웨어과 2학년 |
| student2@demo.dit | 학생 이준서 | 컴퓨터소프트웨어과 2학년 |
| student3@demo.dit | 학생 박서윤 | 시각디자인과 1학년 (타 학과 차단 확인용) |
| assistant@demo.dit | 조교 정민아 | 컴퓨터소프트웨어과 |
| admin@demo.dit | 학사운영팀 | 학교 전체 공지 가능 |

세션은 `sessionStorage`라서 **탭마다 다른 계정**으로 로그인할 수 있습니다. 한 탭은 조교, 다른 탭은 학생으로 열면 공지 자동 배포·채팅 실시간 수신을 바로 확인할 수 있습니다. 데이터 초기화는 데스크톱 사이드바의 "시연 데이터 초기화".

## 구현 범위 (P0 기준)

| 기능 | FR | 경로 |
|---|---|---|
| 로그인/역할별 홈/보호 라우트 | AUTH-001 | `/login` |
| 1. 익명 자유게시판 글 CRUD + 익명 댓글 | COM-001~002 | `/app/community` |
| 2. 실명 팀원 모집 CRUD + 지원/승인(정원 검사) | COM-004~005 | `/app/community?tab=recruit` |
| 3. 기회 저장·준비상태·체크리스트 CRUD | OPP-002~004 | `/app/opportunities` |
| 조교 공지 CRUD → 학과/학년 채널 공식 카드 자동 배포 | NOT-001~002 | `/staff/notices` |
| 학과 전체·학년 채널 채팅, 자유 채널 개설 | DEPT-001~005 | `/app/department` |
| 홈 통합 + 오늘의 브리핑(규칙 기반, AI 미연결) | HOME-001, AI-001 | `/app` |
| 내 시간표 | ACA-001 | `/app/timetable` |

명세의 핵심 규칙 중 반영된 것:
- 익명 글 공개 응답에 작성자 UID/실명이 없는 projection 사용 (`api/community.ts`)
- 공지 카드 중복 방지 키 `(notice_id, revision, channel_id, event_type)`, 원문 복사 없이 참조만 저장, 수정 시 최신판 표시 (`api/notices.ts`)
- 학교 전체 공지는 학과 채팅에 복제하지 않음 (DFLT-004)
- 메시지 `clientNonce`로 재전송 중복 방지, 모집 승인 시 정원을 같은 트랜잭션에서 검사
- 외부 장학금 제출은 "제출했다고 기록"(자기 보고)으로만 표시 (DFLT-006)
- 모든 입력 길이/형식 검증, 권한 위반 시 403 메시지, 로딩/빈/오류/권한 없음 상태

## 구조

```
src/
  app/            라우터, 인증 컨텍스트, 레이아웃(사이드바/하단 탭)
  features/       auth · home · department · notices · community · opportunities
  shared/
    data/store.ts   localStorage 저장소 + 탭 간 실시간 동기화(BroadcastChannel)
    data/api/*      "서버" 계층: 권한·검증·비즈니스 규칙 (화면은 여기만 호출)
    ui/             공통 컴포넌트(Button, Card, Field, ConfirmDialog, Toast …)
```

> 루트 `.gitignore`가 `lib/`를 무시하므로 공용 코드는 `shared/data`에 둡니다.

## 색상

동의과학대학교 홈페이지(dit.ac.kr) CSS에서 추출한 레드(`#c41816`, `#ee302e`)·네이비(`#1b2740`, `#274160`)·스카이(`#06a9dc`) 계열을 `tailwind.config.js` 토큰으로 정의했습니다. 공식 CI 사용권은 미결정(OPEN-008)이므로 참고 색감으로만 사용합니다.

## 다음 단계 (서버 전환)

1. Supabase 프로젝트 생성 → `docs/05_DATA_MODEL.md` 기준 마이그레이션 + RLS
2. `src/shared/data/api/*` 내부를 Supabase 쿼리/Edge Function 호출로 교체 (함수 시그니처 유지)
3. 공지 배포를 `publish-notice` Edge Function + outbox로 이전, 채팅은 Realtime 구독
4. 브리핑에 서버 측 AI 호출 추가 (현재 규칙 결과는 실패 시 대체로 유지)
