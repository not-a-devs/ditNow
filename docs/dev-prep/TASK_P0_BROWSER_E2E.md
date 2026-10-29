# TASK-BROWSER-E2E — P0 공통 로그인→3대 CRUD 브라우저 하네스

> **최신 실행:** 사용자 승인 `DITNOW-P0-DEMO-20261030`으로 실제 생성·로컬 HTTP·390/1280 브라우저와 정리를 수행했다. [실행 SHA·결과](TASK_P0_APPROVED_LIVE_E2E.md)를 따른다. 아래 미실행·승인 대기는 원본 도구 작성 당시 이력이며 운영 배포 승인이 아니다.

> 상태: `review` (하네스 구현). **실제 2계정 브라우저 실행은 NOT_RUN** — root가 로컬 apps/web·API·DEMO 계정을 준비한 뒤에만 실행한다.
> 이 문서와 하네스의 stage PASS는 root 검토용 증거일 뿐이며 VERIFIED·실DB 완료 주장이 아니다.

## 1. 범위와 근거
| 항목 | 내용 |
| --- | --- |
| 기준 | 최초 base `7f7eabb`; 독립 검토 보완에서 PR60의 신규 앱 메모리 로그인·실제 메뉴/가드/논리취소 계약과 PR61의 API 계약을 대조 |
| 소유 경로 | `tests/e2e/**`, `docs/dev-prep/TASK_P0_BROWSER_E2E.md`, `.github/workflows/p0-browser-harness-ci.yml` |
| 수정 안 함 | apps/web 소스·package·공통 client/router/App/NAV/OpenAPI/DB/migration/auth/backend 전부 (`scripts/p0-browser-check.cjs`는 만들지 않음) |
| FR/NFR | FR-AUTH-001, FR-COM-001, FR-COM-004, FR-OPP-004, NFR-SEC-002, NFR-PRIV-001, NFR-DATA-002, NFR-PERF-002 |
| TC | TC-001(로그인/로그아웃), TC-002(익명 CRUD), TC-003 중 모집 생성·수정·종료, TC-004(준비 목록), TC-014(390/1280), TC-018(B의 A 데이터 R/W/U/D) |
| 별도 담당 | HTTP 보안 전수 검사(헤더·토큰 폐기·CORS 등)는 B 담당. 이 하네스는 UI 경로·상태·실제 API 재조회만 본다 |

## 2. 실행 방법 (root 전용)
```sh
cd tests/e2e
npm ci                      # playwright 1.64.1 고정 (ditNow-browser-tools와 동일 버전)
npx playwright install chromium   # 브라우저가 없을 때만, root 판단
npm test                    # 오프라인 하네스 단위 테스트
mkdir -p .artifacts && P0_E2E_RUN=1 ... node run.cjs > .artifacts/report.json   # 실제 실행 (값은 셸에서 주입, .artifacts는 gitignore)
```
| 환경 변수 | 필수 | 규칙 |
| --- | --- | --- |
| `P0_E2E_RUN` | 예 | 정확히 `1`일 때만 실행. 그 외에는 다른 변수를 읽지도 않고 `NOT_RUN`·종료 0·네트워크 없음 |
| `P0_E2E_WEB_URL` | 예 | loopback(`localhost`/`127.0.0.1`/`[::1]`) http(s) origin만. 원격 주소·계정정보·쿼리는 거부 |
| `P0_E2E_API_URL` | 예 | loopback + `/api/v1` 같은 경로 포함 |
| `P0_E2E_STUDENT_A_ID` / `_PASSWORD` | 예 | 고정 DEMO 학생 A |
| `P0_E2E_STUDENT_B_ID` / `_PASSWORD` | 예 | 고정 DEMO 학생 B (A와 달라야 함) |
| `P0_E2E_OPPORTUNITY_ID` | 예 | seed된 DEMO 공고 UUID. A가 이미 저장해 둔 공고면 기존 행을 건드리지 않고 `PRECONDITION` 실패 |
| `P0_E2E_INCLUDE_CLOSE` | 아니오 | `1`이면 별도 표본으로 마감→DELETE 거부를 검사. 마감 표본은 삭제 불가라 잔여물로 보고됨 |
| `P0_E2E_SCREENSHOTS` | 아니오 | 기본 끔. `1`이면 `tests/e2e/.artifacts/`(gitignore)에 저장, 비밀번호 입력 마스킹 |
| `P0_E2E_TIMEOUT_MS` | 아니오 | 1000~60000, 기본 10000 |

종료 코드: `0` PASS 또는 NOT_RUN, `1` FAIL/INCOMPLETE, `2` opt-in 했지만 설정 오류(변수 **이름과 코드만** 보고). 기본 NOT_RUN의 종료0은 실제 E2E 통과가 아니다.

## 3. 안전 장치
- 코드에 계정·비밀번호·토큰 하드코딩 없음. 자격 증명은 private 필드 객체에 보관되어 `JSON.stringify`/`util.inspect`에 노출되지 않는다.
- 보고서는 정적 stage `PASS/FAIL/SKIPPED`와 고정 코드(`TIMEOUT`, `SELECTOR_MISSING`, `HTTP_STATUS`, `ASSERTION`, `PRECONDITION`, `NOT_DEMO` …)만 담는다. Playwright/fetch 오류의 message·stack은 버리고, 하네스가 쓴 설명도 비밀번호·학번·토큰·DEMO 이름·user_id·리소스 ID를 `***`로 마스킹한다. Bearer/JWT/UUID 형태도 일반 마스킹한다.
- trace·video·HAR·응답 본문 덤프를 만들지 않는다. 브라우저 HTTP 리소스는 web/API loopback origin만 허용하고 `route.fetch({maxRedirects:0,maxRetries:0})`로 받은 모든 3xx를 fulfill 전에 차단한다. `route.continue`의 최초 URL 검사만으로 redirect 후속 요청까지 안전하다고 가정하지 않는다. 서비스워커·다운로드를 차단하고, 자격 입력 직전에도 최상위 page URL의 정확한 web origin·`/app/login`·쿼리/fragment 없음을 재검증한다. 브라우저 전체 OS/확장·WebSocket 트래픽까지 검증했다고 주장하지 않는다.
- 별도 API 클라이언트도 `redirect:error`, no-store, omit credentials, no-referrer를 강제하며 API base의 경로 경계·literal dot·encoded dot/slash·backslash·fragment 이탈을 접속 전에 거부한다. [Playwright Route 공식 API](https://playwright.dev/docs/api/class-route#route-fetch)의 maxRedirects=0 동작을 확인했다(2026-10-30).
- 로그인·`/auth/me`가 `record_source: DEMO`가 아니면 브라우저 작업 전에 `NOT_DEMO`로 중단한다. 자기 DTO의 학번·UUID·현재 학과/학년·학생 커뮤니티 자격을 검사하고 공개 공고도 source_kind=DEMO를 확인한다. API 사전검사와 모든 UI 재로그인에서 받은 토큰은 메모리 Set으로 추적·출력 마스킹하고 finally에서 각각 로그아웃 및 GET /auth/me 401까지 확인한다. 확인 실패는 cleanup 실패로 보고한다.
- 생성 리소스 ID는 프로세스 메모리의 registry에만 있고 보고서에는 종류별 개수만 나온다. 제목·체크 문구에 실행마다 다른 `E2EP0-xxxxxxxx` marker를 넣는다.
- 정리는 A 본인 세션으로 **현재 `is_mine` + 이번 marker**인 글만 재조회 후 개별 DELETE한다. 준비 목록도 현재 memo 또는 체크 문구에 이번 marker가 있어야 하며, registry UUID만 같다는 이유로 같은 계정의 나중 재저장 행을 지우지 않는다. marker가 없으면 쓰지 않고 skipped/INCOMPLETE로 남긴다. 목록 일괄 삭제·DB reset 없음, 요청 40회 상한, 항목당 2회 시도. 마감된 모집글은 계약상 삭제 불가라 residual_closed/INCOMPLETE로 보고한다. 체크를 만든 적 없거나 먼저 지운 뒤 실패한 준비 목록은 안전한 자동 정리가 차단될 수 있으며 운영자가 별도로 확인해야 한다.
- 정리 응답 손상·예외가 발생해도 각 브라우저/context 종료와 캡처한 모든 토큰 폐기를 끝까지 시도한다. 예외 원문을 출력하지 않는다. page error·개인 응답 no-store 누락·차단된 외부 요청/redirect·정리 실패는 FAIL, 정리 잔여물·marker 불일치·budget 초과·정리 미확인은 INCOMPLETE여서 종합 PASS가 될 수 없다.

## 4. 실제 동작 (뷰포트 390·1280 각각, 새 컨텍스트)
| stage | 검사 |
| --- | --- |
| `preflight.demo_accounts` | 하네스 자체 API 세션으로 A·B 로그인 + `/auth/me`, DEMO·서로 다른 user 확인 |
| `preflight.opportunity` | 공개 GET `/opportunities/{id}`, A 미저장 확인, B 저장 여부 기록 |
| `auth.login_a` | `/app/login` 폼 입력→브라우저가 POST `/auth/login` 200과 GET `/auth/me` 200을 실제 수신→본인 표시 이름 노출 |
| `community.anonymous.create_edit_reload` | UI 작성(201)→API 목록 재조회 `is_mine`·`익명`·작성자 신원 미포함→UI 수정(PATCH 200)→새로고침→UI·API 단건 재조회 제목/revision 증가 |
| `community.recruitment.create_edit_reload` | UI 작성(201)→재조회 open→UI 수정→새로고침→API 필드·revision 확인 |
| `opportunity.save_check_update_reload` | 공고 검색·선택→저장(PUT 201)→체크 추가(201)→완료 토글(PATCH)→상태 변경(If-Match PATCH)→새로고침→UI 체크 유지·API 재조회 |
| `isolation.student_b` | B 별도 컨텍스트 로그인→A 익명글은 `익명`·수정/삭제 버튼 없음, A 모집글 소유자 버튼 없음, B 준비 목록에 A 체크 없음→B 토큰으로 A 글/모집 PATCH·DELETE·close, A 저장 PATCH 시도는 403/404→A 재조회로 무변경 확인 |
| `community.anonymous.delete` | UI 삭제(DELETE `?revision`)→새로고침 목록 없음→API GET 404 |
| `community.recruitment.delete` | UI 삭제(DELETE `/{id}?revision=N`)→응답 `data{id,deleted:true}`→새로고침 목록 없음→API GET 404·목록 숨김 |
| `opportunity.remove` | 체크 삭제→`목록에서 삭제`→새로고침→API 목록에 없음 |
| `community.recruitment.close_not_deletable` | (opt-in) 별도 표본 작성→`모집 마감`→API closed→DELETE 4xx(401 제외)→여전히 closed |
| `auth.logout_a` | `로그아웃`→브라우저가 POST `/auth/logout` 200 수신→보호 화면의 명시적 로그인 필요 안내·버튼 확인→`/app/login`의 폼 확인 |

관찰값(뷰포트별 개수만): console error, page error, 차단된 외부 HTTP 요청/redirect/리소스 실패, `no-store` 없는 개인 응답, 새로고침 후 세션 동작(`relogin_required`). 현재 메모리 세션이 자동 복원되는 경우를 성공으로 허용하지 않는다.

## 5. 현재 화면·API 계약 대조 결과
Q-*는 기존 진단 코드로 보존한다. 아래 확인은 코드 계약 대조이며 실제 2계정 E2E 실행 증거가 아니다. mock 런타임으로 대체하지 않았다.

| ID | 대상 | 질문 / 하네스 가정 |
| --- | --- | --- |
| Q-F1 | F | PR60: `/app/login`, `가상 학번`·`비밀번호`, `가상 계정으로 로그인` 유지 |
| Q-F2 | F | 로그인 후 GET `/auth/me`의 현재 display_name·user_id·DEMO 응답과 화면 표시를 대조 |
| Q-F3 | F/root | 메모리 세션은 새로고침 후 폐기. 보호 route의 `로그인이 필요한 화면입니다`→`로그인 화면으로`→`/app/login`→로그인→원래 메뉴 재탐색 |
| Q-F4 | F | open 본인 글: `모집글 취소 · 목록에서 제거` + window.confirm → DELETE `?revision=N`. 물리 삭제가 아닌 cancelled 논리 취소. closed에는 취소 버튼 없음 |
| Q-F5 | F | `로그아웃` 버튼이 보호 화면(390은 메뉴 열기 `button[aria-controls="campus-navigation"]` 이후 포함)에서 접근 가능한가 |
| Q-F6 | F | 보호 route는 자동 redirect나 폼을 렌더하지 않음. 위 Q-F3의 명시적 안내와 로그인 버튼을 거쳐야 함 |
| Q-F7 | F | 익명 게시판 `/app/community`(섹션 `anon-heading`), 모집 `/app/recruitments`(섹션 `recruit-heading`), 기회 `/app/opportunities`(섹션 `opp-saved`)에 기존 모듈을 마운트하고 사이드바 링크 이름을 유지하는가. 탭이 있으면 하네스가 클릭 |
| Q-A1 | A | `/auth/login`·`/auth/me`의 DEMO 표시 필드명이 `record_source: "DEMO"`인가, `/auth/me`에 `user_id`·`display_name`이 있는가 |
| Q-A2 | A | closed 모집 DELETE의 정확한 상태 코드(409 예상). 하네스는 401 제외 4xx 허용 |
| Q-A3 | A | 타인 리소스 수정/삭제/마감 응답이 403인지 404인지. 하네스는 둘 다 허용 |
| Q-R1 | root | web→API CORS(로컬 origin), 로컬 실행 포트, DEMO 계정 2개·공고 UUID 주입 시점 |

## 6. 실제 검사 결과 (이 브랜치)
| 명령 | 결과 |
| --- | --- |
| `cd tests/e2e && npm install --package-lock-only --ignore-scripts --offline` | 성공, lock 생성 (playwright·playwright-core 1.64.1) |
| `npm ci --ignore-scripts --offline` | 성공, 2 packages |
| `node --test "test/*.test.cjs"` | 최초19개 PASS; 독립 검토 보완 후 최종37개 PASS. 이 테스트들은 페이지·전송 double을 사용하는 오프라인 하네스 회귀이며 실제 브라우저 통과가 아님 |
| `npm audit --audit-level=moderate` | PASS, 취약점0 |
| `node run.cjs` (env 없음) | `NOT_RUN` / `OPT_IN_MISSING`, stages 0, 네트워크·브라우저 없음 |
| 실제 2계정 브라우저 E2E (390/1280) | **NOT_RUN by harness authors/reviewer** — root의 격리 서버·승인 DEMO 계정으로 별도 실행 필요 |
| `.github/workflows/p0-browser-harness-ci.yml` | 로컬 NOT_RUN, PR CI에서 확인 |

## 7. 남은 게이트
- 소스 대조와 오프라인 회귀를 완료했으나 실제 브라우저에서 locator·리디렉션 거부·CORS·후속 재조회가 함께 작동하는지는 아직 NOT_RUN이다. 한 번의 stage 실패를 무시하거나 mock으로 대체해 통과시키지 않는다.
- root가 로컬 apps/web·API·DEMO seed를 띄우고 `P0_E2E_RUN=1`로 실제 실행 → 보고서 JSON을 검토. 실DB(MariaDB) 근거는 DB 게이트에서 별도로 판정.
- HTTP 보안 전수 검사(B), Lighthouse(TC-015)는 이 하네스 범위 밖.
- 현재 공유 요청 제한 기본값20/분으로 전체 390·1280 흐름과 토큰 정리가 429에 걸릴 수 있다. root가 **격리된 로컬 검증 서버**의 명시적 quota/페이싱을 승인·구성해야 한다. 하네스가 서버 제한을 자동 변경하거나 429를 성공으로 무시·무한 재시도하지 않는다. 이는 운영 정책이나 비용·배포 승인 완화를 뜻하지 않는다.
