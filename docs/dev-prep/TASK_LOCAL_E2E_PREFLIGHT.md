# TASK-LOCAL-E2E-PREFLIGHT — 실제 통합 검증의 로컬 사전 점검

2026-10-30 KST · 기준 `f8705eac26dc12960b2689e894497e9893371ca5` · 상태 **TESTED(로컬 미인증 범위) / 실제 2계정·DB E2E는 BLOCKED_APPROVAL·NOT_RUN**.

## 범위와 경계

- 변경은 이 문서 하나다. 신규 `apps/web/`, FastAPI, 하네스, 인증·DB·승인 pin·migration·NAV를 수정하지 않았다. 기존 worktree와 미커밋 파일을 보존했다.
- FR-AUTH-001/002의 실패 안전·현재 신원 차단 부분, FR-COM-001/004 및 FR-OPP-004의 선행 환경만 점검한다. NFR-SEC-001/002/004/005, NFR-PRIV-001/003, NFR-UX-001/003, TC-001/014/016/017의 일부다. 핵심 CRUD·권한 격리 자체의 통과 증거가 아니다.
- DB·비밀정보·DPAPI에 접근하지 않았고 계정·승인 감사행·공고·관리자·세션을 생성하지 않았다. P0 인증·DB 런타임 활성화와 가상 계정 생성은 별도 명시 승인 전 실행하지 않는다. `mvp/` 코드를 참조·복사하지 않았다.
- [브라우저 하네스](TASK_P0_BROWSER_E2E.md), [HTTP 보안 검사](TASK_P0_SECURITY_E2E.md), [API 런타임](TASK_P0_LIVE_API_IMPLEMENTATION.md), [가상 계정 운영](TASK_DEMO_ACCOUNT_OPS.md)을 대조했다.

## 실제 환경·설치

| 항목 | 실제 결과 |
| --- | --- |
| Node / Python | Node 22.14.0, Python 3.13.3 |
| API 잠금 설치 | `uv sync --locked --offline` PASS. 새 worktree의 격리 venv·editable chatbot 패키지 사용 |
| 신규 웹 잠금 설치 | `npm ci --offline` PASS, 취약점0 |
| 하네스 설치 | `cd tests/e2e`, `npm ci --ignore-scripts --offline` PASS. Playwright 1.64.1, 브라우저 다운로드 없음 |
| 설치된 브라우저 | Chromium cache revision1248로 실제 headless 실행, 버전156.0.8078.4 |
| 하네스 오프라인 검사 | `npm test` **37 PASS / 0 FAIL** |
| 하네스 기본 실행 | `node run.cjs`: NOT_RUN / OPT_IN_MISSING, stage0, verified_claim=false. `P0_E2E_RUN=1`은 실행하지 않음 |
| 신규 앱 프로덕션 빌드 | 로컬 API base를 명시한 `npm run build` PASS(타입 검사 포함) |

## 실제 로컬 HTTP 점검

사용하지 않는 loopback 포트5753(web)·8753(API)를 먼저 확인했다. API는 작업 전용 프로세스에서 `DIT_API_*` 및 legacy DB 설정 환경을 제거하고, `Settings(environment="development", cors_origins=["http://127.0.0.1:5753"], _env_file=None)`로 생성했다. DB 설정·engine·LLM이 없고 `p0_runtime_enabled=false`, `p0_schema_approved=false`, 승인 pin 비어 있음·platform runtime 없음임을 실행 전에 확인했다. 비밀값을 읽어 확인한 것이 아니다.

자기 서버만 `127.0.0.1`에 열었으며 외부 공개·DB 컨테이너 생성은 없다. 테스트 입력은 존재하는 계정 자격이 아닌 합성 문자열이었다. DB 엔진이 없으므로 계정 인증·토큰 발급으로 진행하지 않았다. 프록시 환경·redirect를 사용하지 않는 실제 localhost HTTP 클라이언트로 다음 **11개**를 확인했다.

| 경로·조건 | 실제 응답 | 해석 |
| --- | --- | --- |
| GET `/health`, `/api/v1/health` | 각각200 | 프로세스 생존만 확인, 인증·DB 준비 증거 아님 |
| GET `/api/v1/auth/me` | 503 + private, no-store | 공통 원장 미활성 상태를 성공으로 표시하지 않음 |
| POST `/api/v1/auth/login`, `/api/v1/auth/logout` | 각각503 + private, no-store | DB·세션 공급자 미준비, 가상 로그인도 수행되지 않음 |
| GET `/api/v1/anonymous-posts`, `/api/v1/recruitments`, `/api/v1/me/saved-opportunities` | 각각404 + private, no-store | 기본 비활성인 조건부 업무 라우터. 운영 시의 401/권한 격리 검증이 아님 |
| GET `/openapi.json` | 404 | 기본 문서 비공개 유지 |
| 허용된 web origin의 DELETE preflight, Authorization/If-Match/Idempotency-Key | 200, 정확한 allow-origin, credentials 허용 없음 | 명시 CORS 경계 |
| 다른 localhost 포트 origin의 같은 preflight | 400, allow-origin 없음 | wildcard·다른 origin 허용하지 않음 |

실제 GET·POST에도 정확한 허용 CORS 헤더를 확인했다. 실제 계정의 학적·개인 데이터나 다른 사람의 레코드를 읽지 않았다.

## 실제 브라우저 점검: 390·1280

하네스의 `openInstrumentedPage`를 그대로 사용해 service worker 차단·HTTP redirect0 리소스 처리 아래 신규 앱을 열었다. credential E2E 시나리오 전체나 RUN1 실행은 아니다.

1. `/app/community` 직접 진입 시 `로그인이 필요한 화면입니다`와 `로그인 화면으로`가 보이고 개인 모듈·로그인 폼은 없다. 보호 API 요청은0건이었다.
2. 버튼으로 `/app/login` 이동, 입력 초기값이 비어 있음을 확인했다. 합성 입력 제출은 실제 POST login503을 받았고, 실패 안내가 표시되며 비밀번호가 지워졌다. Authorization 헤더·토큰 저장은 없고 후속 `/auth/me` 요청도0건이었다.
3. 홈의 공개 서버 연결 확인은 실제 `/api/v1/health`200으로 응답했다. UI는 인증·DB 상태를 확인한 것이 아니라고 표시한다.
4. 두 폭 모두 document scrollWidth가 viewport와 같고, localStorage/sessionStorage 항목0, page error0, 외부 HTTP 요청/차단 redirect/리소스 차단 오류0, private no-store 누락0이었다. 390 로그인·보호 안내와1280 로그인 스크린샷을 직접 확인했다. 스크린샷·임시 실행기·로그는 저장소 밖 로컬 임시 산출물이며 커밋하지 않는다.

### 개발 서버 콘솔과 preview 구분

- Vite dev에서는 viewport마다 console error9개(의도한 login503 1, dev WebSocket 분류6, 기타2)가 관찰됐다. 기타2의 상세 원인은 확정하지 않았으며 이를 오류0으로 숨기지 않는다.
- 같은 소스를 빌드한 **loopback preview**로 검증하니 console error는 예상한 login503 리소스 오류1개만 남았다. dev WebSocket/기타 오류0, page error0이었다. 기능 성공으로 실패 응답을 바꾼 것이 아니다.
- 따라서 실제 운영자 E2E에는 HMR이 없는 로컬 build+preview를 우선 사용하고, 콘솔의 의도한 실패 응답과 JS 실행 오류를 구분해 기록한다. 앱·하네스 코드를 임의로 수정하지 않았다.
- 테스트 종료 후 포트·PID·명령이 이 작업이 생성한 프로세스인지 확인하고 API와 preview를 종료했다. 두 loopback listener가 해제됐음을 확인했다.

## 승인 이후의 실행 준비 — 아직 실행하지 않음

### 1. 계정·원장·런타임 게이트

- 운영 담당자가 [가상 계정 운영 절차](TASK_DEMO_ACCOUNT_OPS.md)의 생성·승인 감사행과 정확한 issuer/subject→canonical UUID 매핑을 명시 승인한다. PR 병합은 실제 계정 생성이나 pin 활성화 승인이 아니다. 실제 학교 학번·비밀번호를 입력하지 않는다.
- 서로 다른 DEMO 학생 A/B와 학과·현재 학생 역할, 승인된 canonical 표시 이름, 운영자가 검토한 감사행 ID가 필요하다. 별도 사용자 원장을 복제하거나 관리자 역할을 학생에게 만들지 않는다. 비활성 operator 증빙과 감사 pin의 의미는 기존 계약을 따른다.
- strict TLS/CA·`ditnow_app` 최소 권한·16테이블 스키마와 기존 원장 보존을 운영자가 재확인한다. 이 사전 점검이 그 검증을 대체하지 않는다. DB 자격과 CA 경로는 로컬 비밀 주입으로만 제공한다.
- 실제 활성화에는 `DIT_API_DB_HOST/PORT/NAME/USER/PASSWORD/TLS_CA_FILE`에 대응하는 완전한 DB 설정, `DIT_API_ENVIRONMENT`, `DIT_API_P0_RUNTIME_ENABLED`, `DIT_API_P0_SCHEMA_APPROVED`, `DIT_API_P0_IDENTITY_APPROVAL_IDS`의 승인된 조합이 필요하다. DB 키는 각각 전체 `DIT_API_DB_` 접두사를 가진다. 기본값을 바꾸거나 추정 UUID로 pin하지 않는다.
- 승인된 DEMO 기회 UUID와 제목 marker `DITNOW_DEMO_P0_INTEGRATION`, source_kind=DEMO·info_only 공고가 필요하다. 외부 공고나 기존 개인 준비 행을 자동 선택하지 않는다.

### 2. URL·CORS·실행 변수

| 주체 | 필요한 설정·경계 |
| --- | --- |
| 신규 웹 | 빌드 시 `VITE_API_BASE_URL=http://127.0.0.1:<api-port>/api/v1` 같은 명시 로컬 base. 비밀값이 아니며 토큰을 넣지 않음 |
| API | `DIT_API_CORS_ORIGINS`에 web의 정확한 scheme/host/port만. localhost와127.0.0.1도 서로 다른 origin이다. wildcard·쿠키 credentials 허용 안 함 |
| 브라우저 하네스 | `P0_E2E_RUN`, `P0_E2E_WEB_URL`(origin), `P0_E2E_API_URL`(`/api/v1` 포함), `P0_E2E_STUDENT_A_ID`, `P0_E2E_STUDENT_A_PASSWORD`, `P0_E2E_STUDENT_B_ID`, `P0_E2E_STUDENT_B_PASSWORD`, `P0_E2E_OPPORTUNITY_ID`. 승인 후에만 로컬 프로세스 환경으로 주입 |
| HTTP 보안 검사 | `DIT_API_RUN_P0_SECURITY_CHECK`, `DIT_API_P0_SECURITY_CHECK_APPROVED`, `DIT_API_P0_CHECK_BASE_URL`(API origin만, `/api/v1` 제외), `DIT_API_P0_CHECK_A_STUDENT_ID`, `DIT_API_P0_CHECK_A_PASSWORD`, `DIT_API_P0_CHECK_B_STUDENT_ID`, `DIT_API_P0_CHECK_B_PASSWORD`, `DIT_API_P0_CHECK_OPPORTUNITY_ID`, `DIT_API_P0_CHECK_OPPORTUNITY_MARKER` |
| 생성물 | screenshots/close sample은 기본 OFF. 비밀값을 argv·저장소·공유 로그·URL에 기록하지 않음 |

현재 Vite 설정에는 `/api/v1` 프록시가 없다. 같은 origin 구조를 선택한다면 배포 담당자의 승인된 reverse proxy가 해당 경로를 FastAPI로 전달해야 한다. 기본 상대경로만으로 Vite가 API 서버가 되는 것은 아니다. 위 실제 검증은 **명시 API base + 명시 CORS** 방식만 확인했다.

### 3. 실행·증거 단계

1. 운영자 승인과 합성 원장 준비를 확인한 뒤 로컬 한정 서버를 켜고 `/health`·실제 `/auth/me`·명시 CORS·no-store를 재확인한다. 인증 성공은 검증된 현재 신원 DTO까지 확인해야 한다.
2. 요청 제한 기본20/분으로는 두 viewport·반복 재로그인·마지막 모든 세션 정리가 429에 걸릴 수 있다. 운영자가 **격리 로컬 검증 서버의 명시 quota 또는 페이싱**을 승인·설정한다. 하네스가 제한을 변경·우회·자동 무한 재시도하지 않는다. 유료 LLM이나 배포를 켜지 않는다.
3. HTTP 보안 검사에서 A 생성·재조회·수정·논리 삭제/취소, CAS·멱등성·익명 projection, B 타인 쓰기 거부·개인 목록 격리·재로그인·세션 폐기를 확인한다. 결과는 해당 HTTP 범위의 증거다.
4. 브라우저에서 390/1280 로그인→세 CRUD→전체 새로고침 후 명시 재로그인→현재 신원·재조회→B 별도 컨텍스트 격리→본인 marker 정리·로그아웃을 수행한다. 메모리 세션의 자동 복원을 성공으로 허용하지 않는다.
5. 정리 중 현재 marker가 없거나 손상·불명확 응답·닫힌 모집 잔여물·토큰 폐기 미확인이 있으면 FAIL/INCOMPLETE를 보존한다. 대량 삭제나 DB reset으로 지우지 않는다. close 샘플은 별도 보존 승인이 없는 한 OFF다.
6. 마지막에 정확한 SHA·실행 환경·각 단계 결과·정리 상태·남은 NOT_RUN을 기록한다. 새 HTTP 세션의 재조회는 서버 재시작·배포 환경 영속성·동시성 전체의 증거가 아니며 각각 별도 검증한다.

## 남은 차단과 다음 작업

실계정 로그인·현재 권한 재검증·MariaDB CRUD·두 계정 격리·서버 재시작 영속성·배포·Lighthouse는 **NOT_RUN**이다. 차단 원인은 아직 이 작업에 부여되지 않은 계정 생성/승인 pin/runtime 활성화의 명시 승인과 비밀 주입이다. 실행 가능한 로컬 미인증 사전 점검은 완료했으며, 다음은 운영자 승인 이후의 실제 2계정 수직 통합 검증이다. 전체 92개 기능 진척을 VERIFIED로 올리지 않는다.
