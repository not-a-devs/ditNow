# DIT NOW 신규 통합 웹

TASK-B-WEB-SHELL · React + TypeScript + Vite + Tailwind CSS 신규 앱이다. 기존 `mvp/` 구현과 별도로 작성했으며 해당 앱의 코드·데이터·스타일을 가져오지 않았다. 기존 앱의 이동·삭제는 수행하지 않는다.

## 실행

Node.js 22.12 이상(22 계열) 또는 24 이상을 사용한다. DB 제품은 DEC-016의 MariaDB이며 이 앱은 DB에 직접 연결하지 않는다.

```text
cd apps/web
npm ci
npm run dev -- --port 5181
```

`/app`이 통합 홈이다. `/`도 홈을 표시한다. 호스팅 도입 시 `/app/*`의 SPA fallback 구성이 필요하며 배포는 이 작업 범위에 없다. 외부 폰트·분석·유료 자산을 사용하지 않는다.

공개 API는 기본적으로 같은 origin의 `/api/v1`로 요청한다. API가 다른 origin에서 실행되면 `.env.example`의 `VITE_API_BASE_URL`에 `http://127.0.0.1:8000/api/v1` 같은 절대 HTTP(S) 기본 주소를 설정하고 FastAPI의 CORS origin도 별도로 허용한다. `VITE_*` 값은 브라우저에 공개되므로 비밀값을 넣지 않는다. 현재 CORS·인증 공급자를 선택한 것으로 해석하지 않는다.

## 구현 상태와 범위

| 영역 | 상태 | 실제 동작 / 검증 범위 |
| --- | --- | --- |
| 통합 홈을 포함한 10개 메뉴 내비게이션 | IMPLEMENTED / TESTED | History API 이동, 뒤로가기, 잘못된 경로, 모바일 전체 메뉴 |
| 디자인·공통 상태 | IMPLEMENTED / TESTED | 공개 탐색·미인증·미구현 안내, 키보드 포커스·본문 건너뛰기, 로딩·실패·재시도 |
| 공개 health 요청 | IMPLEMENTED / TESTED | `/api/v1/health` 실제 서버 계약을 호출. 서버 실행·CORS 설정이 필요하며 DB 준비 상태를 판단하지 않음 |
| API 전송 계층 | IMPLEMENTED / TESTED | 성공 응답 `data` 반환, 오류 코드/HTTP 상태/요청 ID, 10초 중단, 안전한 오류, 기본 same-origin credentials |
| OpenAPI 타입 | IMPLEMENTED / TESTED | `services/api/openapi.json`의 현재 공개 경로만 생성·변경 검사 |
| AI 메뉴의 공개 시설 검색 | IMPLEMENTED / TESTED | `/app/ai`에서 FastAPI 공개 검색 API를 호출. 기존 RAG 검색기 재사용, 출처 UNKNOWN·개인 질문 미연결 표시. LLM 생성·학적 조회·로그인은 미구현 |
| 공개 대학·학과 안내 | IMPLEMENTED / TESTED (공개 읽기 범위) | `/app/information`에서 실제 FastAPI의 7개 자체 편집 요약을 검색·분류·페이지 이동·상세로 조회. 출처 존재 VERIFIED/규칙 PARTIAL/최신성 UNKNOWN. 콘텐츠 운영 업무와 전체 6개 FR은 PARTIAL |
| 학사·강의실·학과·커뮤니티·모집·기회·학생지원 업무 | DOCUMENTED / NOT_RUN | 현재는 별도 기능 모듈이 합류하기 전 안내 화면. 실제 CRUD나 학적·인증을 구현했다고 표시하지 않음 |

이 앱은 로그인·세션·학적·관리자 권한을 생성하지 않는다. 가상 로그인 버튼이나 학교 공식 인증 표시도 없다. 홈의 개인 일정/알림은 빈 안내이며 가짜 개인 학사 기록을 넣지 않는다. 화면이 존재한다는 이유로 기존 92개 FR을 완료 처리하지 않는다. 관련 기준은 FR-HOME-001, FR-HOME-002, FR-HOME-003 및 NFR-UX-001~005, NFR-PERF-002, NFR-SEC-004, NFR-OPS-002다. TC-WEB-SHELL-001(내비), 002(연결 상태), 003(안전 오류), 004(경로 제한)를 단위 테스트 27개에서 확인한다.

2026-10-30 로컬 Playwright 1.64.1/Chromium 캐시 브라우저로 실제 Vite 화면을 390px·1280px에서 확인했다. 가로 scrollWidth는 각각 viewport와 동일하고, 본문 건너뛰기 키보드 포커스·모바일 전체 메뉴·커뮤니티 이동·브라우저 뒤로가기·연결 실패/재시도 표시가 통과했다. pageerror는 두 크기 모두 0건이며 전체 화면 캡처를 시각 확인했다. 도구와 캡처는 저장소 밖 임시 경로에 두었다. 이 검사는 실제 FastAPI와 성공적으로 연결하거나 업무 CRUD를 검증한 결과가 아니다.

## 병렬 모듈 계약

`src/features/*/index.tsx`에서 기본 React component를 export하는 독립 모듈을 통합할 수 있다. `ai` 공개 시설 검색과 `public-campus` 공개 대학·학과 안내는 연결했다. 나머지 기능 모듈이 존재해도 공통 인증·DB·권한과 실제 화면 연결을 검증하기 전에는 전역 업무를 완료 처리하지 않는다.

### 공개 시설 검색 검증 (TASK-F-WEB)

관련 범위는 FR-CAMP-001/003의 시설 검색 부분, TC-V1-CAMP-001/003, NFR-UX-001/003/005, NFR-AI-002/003, NFR-PRIV-002/003이다. 예약·지도·개인 AI 브리핑 전체의 완료를 뜻하지 않는다.

- 시설 검색은 실제 FastAPI 응답을 사용한다. API가 꺼지거나 잘못된 응답을 반환하면 안전한 오류를 표시하며 가상 성공 결과를 만들지 않는다.
- 검색 결과의 `retrieval_only`, `generated=false`, `personal_data_access=false`, `verification=UNKNOWN`과 필수 필드를 런타임 검증한 후 렌더링한다. 요청 취소·길이 제한·출처 표시를 검사한다.
- 2026-10-30 로컬 실제 Chromium 390px/1280px에서 신규 Vite→FastAPI 한글 검색·빈 결과·API 404 안전 오류·재검색 성공을 확인했다. 명시한 CORS origin의 GET 허용과 허용되지 않은 origin의 CORS 헤더 부재를 확인했다. 가로 넘침 없음, 페이지 오류 없음, 두 화면 스크린샷을 직접 검토했다.
- 외부 LLM·실사용자·학적 원장·MariaDB·운영 배포는 이 검증에서 사용하지 않았다. 로그인·실DB CRUD·배포와 전체 92개 완성은 아직 차단/미검증 범위를 유지한다.

공통 클라이언트는 `src/lib/api.ts`에서 `requestData<T>(path, init?)`, `ApiError(code,status,requestId?)`를 제공한다. 경로는 `/anonymous-posts`처럼 기본 주소 이후 경로다. 전체 URL·`//`·기본 경로를 벗어나는 요청은 거부한다. 서버가 반환한 비밀값 가능 오류 원문과 네트워크 예외 원문은 사용자에게 출력하거나 기록하지 않는다. 요청 body와 response data는 아직 런타임 도메인 검증을 하지 않으며 각 실제 기능의 입력/출력 모델에서 검증해야 한다.

## 검증과 타입 갱신

TASK-I 통합 후 로컬 전체148개 Vitest·타입 검사·빌드·생성 타입 비교를 통과했다. 실제 Chromium 390px/1280px에서 API 연결·한글/주제/출처 검색·목록/자체 상세·근거/한계 표시·페이지 이동·빈 결과·503 안전 오류/재시도·404/쓰기405·명시적 CORS를 확인했다. 가로 넘침/페이지 오류는 없었고 모바일 상세 제목의 초점 가림을 수정했다. 공개 조회 외의 운영 업무·로그인·DB·배포 완료를 뜻하지 않는다. 상세는 [TASK-I 기록](../../docs/dev-prep/TASK_PUBLIC_CAMPUS_IMPLEMENTATION.md)을 본다.

```text
npm run api:types
npm run api:types:check
npm run typecheck
npm run test
npm run build
npm audit --audit-level=moderate
```

OpenAPI 생성기는 앱 디렉터리의 신규 스크립트로 구현됐다. FastAPI 스냅샷의 변경 시 `npm run api:types` 후 생성 결과를 커밋한다. 타입 검사 시 미구현 인증/도메인 API를 생성 결과에 수동으로 추가하지 않는다. 브라우저 HTTP 요청을 검증할 때 서버를 별도로 실행하고 CORS 또는 같은 origin 프록시를 설정한다.

설치 의존성은 잠금 파일로 고정한다. [Vite 시작 안내](https://vite.dev/guide/), [Vitest 안내](https://vitest.dev/guide/), [Tailwind Vite 설치](https://tailwindcss.com/docs/installation/using-vite)를 확인했다(2026-10-30). OpenAPI 생성기의 TypeScript 5 peer 범위를 맞추어 5.9.3을 선택했다. 테스트 환경의 jsdom은 Node22.14에서 실행 가능한 27.0.1을 고정했다. 운영 인증·호스팅·학사 정책은 이 선택으로 확정하지 않는다.
