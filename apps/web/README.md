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
| 통합 홈·9개 영역 내비게이션 | IMPLEMENTED / TESTED | History API 이동, 뒤로가기, 잘못된 경로, 모바일 전체 메뉴 |
| 디자인·공통 상태 | IMPLEMENTED / TESTED | 공개 탐색·미인증·미구현 안내, 키보드 포커스·본문 건너뛰기, 로딩·실패·재시도 |
| 공개 health 요청 | IMPLEMENTED / TESTED | `/api/v1/health` 실제 서버 계약을 호출. 서버 실행·CORS 설정이 필요하며 DB 준비 상태를 판단하지 않음 |
| API 전송 계층 | IMPLEMENTED / TESTED | 성공 응답 `data` 반환, 오류 코드/HTTP 상태/요청 ID, 10초 중단, 안전한 오류, 기본 same-origin credentials |
| OpenAPI 타입 | IMPLEMENTED / TESTED | `services/api/openapi.json`의 현재 공개 경로만 생성·변경 검사 |
| 학사·강의실·학과·커뮤니티·모집·기회·학생지원·AI 업무 | DOCUMENTED / NOT_RUN | 현재는 별도 기능 모듈이 합류하기 전 안내 화면. 실제 CRUD나 학적·인증을 구현했다고 표시하지 않음 |

이 앱은 로그인·세션·학적·관리자 권한을 생성하지 않는다. 가상 로그인 버튼이나 학교 공식 인증 표시도 없다. 홈의 개인 일정/알림은 빈 안내이며 가짜 개인 학사 기록을 넣지 않는다. 화면이 존재한다는 이유로 기존 92개 FR을 완료 처리하지 않는다. 관련 기준은 FR-HOME-001, FR-HOME-002, FR-HOME-003 및 NFR-UX-001~005, NFR-PERF-002, NFR-SEC-004, NFR-OPS-002다. TC-WEB-SHELL-001(내비), 002(실제 연결 상태), 003(안전 오류), 004(경로 제한)를 단위 테스트에서 확인한다. 실제 390px/1280px 시각 검증은 별도 실행 전까지 NOT_RUN이다.

## 병렬 모듈 계약

`src/features/{community,opportunities,campus,ai}/index.tsx`에서 기본 React component를 export하는 독립 모듈을 통합할 수 있다. 현재 없는 파일을 import하지 않는다. 모듈 구현·합류 후 셸의 안내 화면을 실제 모듈로 교체하고 각 업무 흐름을 별도로 검증한다.

공통 클라이언트는 `src/lib/api.ts`에서 `requestData<T>(path, init?)`, `ApiError(code,status,requestId?)`를 제공한다. 경로는 `/anonymous-posts`처럼 기본 주소 이후 경로다. 전체 URL·`//`·기본 경로를 벗어나는 요청은 거부한다. 서버가 반환한 비밀값 가능 오류 원문과 네트워크 예외 원문은 사용자에게 출력하거나 기록하지 않는다. 요청 body와 response data는 아직 런타임 도메인 검증을 하지 않으며 각 실제 기능의 입력/출력 모델에서 검증해야 한다.

## 검증과 타입 갱신

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
