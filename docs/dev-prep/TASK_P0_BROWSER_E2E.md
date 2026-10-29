# TASK-BROWSER-E2E — P0 공통 로그인→3대 CRUD 브라우저 하네스

> 상태: `review` (하네스 구현). **실제 2계정 브라우저 실행은 NOT_RUN** — root가 로컬 apps/web·API·DEMO 계정을 준비한 뒤에만 실행한다.
> 이 문서와 하네스의 stage PASS는 root 검토용 증거일 뿐이며 VERIFIED·실DB 완료 주장이 아니다.

## 1. 범위와 근거
| 항목 | 내용 |
| --- | --- |
| 기준 | base `7f7eabb`, API(A)·FE(F)가 공통 로그인→3대 CRUD를 병렬 구현 중 |
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

종료 코드: `0` PASS 또는 NOT_RUN, `1` FAIL, `2` opt-in 했지만 설정 오류(변수 **이름과 코드만** 보고).

## 3. 안전 장치
- 코드에 계정·비밀번호·토큰 하드코딩 없음. 자격 증명은 private 필드 객체에 보관되어 `JSON.stringify`/`util.inspect`에 노출되지 않는다.
- 보고서는 정적 stage `PASS/FAIL/SKIPPED`와 고정 코드(`TIMEOUT`, `SELECTOR_MISSING`, `HTTP_STATUS`, `ASSERTION`, `PRECONDITION`, `NOT_DEMO` …)만 담는다. Playwright/fetch 오류의 message·stack은 버리고, 하네스가 쓴 설명도 비밀번호·학번·토큰·DEMO 이름·user_id·리소스 ID를 `***`로 마스킹한다. Bearer/JWT/UUID 형태도 일반 마스킹한다.
- trace·video·HAR·응답 본문 덤프를 만들지 않는다. 브라우저 컨텍스트는 web/API loopback origin 외 요청을 모두 차단하고 개수만 기록한다. 서비스워커·다운로드 차단.
- 로그인·`/auth/me`가 `record_source: DEMO`가 아니면 브라우저 작업 전에 `NOT_DEMO`로 중단한다.
- 생성 리소스 ID는 프로세스 메모리의 registry에만 있고 보고서에는 종류별 개수만 나온다. 제목·체크 문구에 실행마다 다른 `E2EP0-xxxxxxxx` marker를 넣는다.
- 정리는 A 본인 세션으로 **이번 실행이 만든 것 또는 `is_mine` + 이번 marker**인 것만 재조회 후 개별 DELETE한다. 목록 일괄 삭제·DB reset 없음, 요청 40회 상한, 항목당 2회 시도. 마감된 모집글은 계약상 삭제 불가라 `residual_closed`로 보고한다.

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
| `auth.logout_a` | `로그아웃`→브라우저가 POST `/auth/logout` 200 수신→보호 화면 이동 시 로그인 폼 |

관찰값(뷰포트별 개수만): console error, page error, 차단된 외부 요청, `no-store` 없는 개인 응답, 새로고침 후 세션 동작(`restored`/`relogin_required`).

## 5. F·A·root 확인 질문 (하네스가 가정한 계약)
기존 화면(community/opportunities/auth/navigation)의 라벨은 그대로 사용했다. 아래는 아직 없는 화면 계약이며, 실패 시 보고서 detail에 질문 ID가 찍힌다. mock 런타임으로 대체하지 않았다.

| ID | 대상 | 질문 / 하네스 가정 |
| --- | --- | --- |
| Q-F1 | F | `/app/login`이 직접 진입 시 로그인 폼을 렌더하고 기존 라벨 `가상 학번`·`비밀번호`, 버튼 `가상 계정으로 로그인`을 유지하는가 (enabled=true로 연결) |
| Q-F2 | F | 로그인 성공 후 FE가 GET `/auth/me`를 호출하고 그 `display_name`을 화면 어딘가에 텍스트로 표시하는가. 별도 `data-testid`를 둘지 결정 필요 |
| Q-F3 | F/root | 전체 새로고침 후 세션 정책: 메모리 세션이라 재로그인 요구인가, 복원인가. 하네스는 둘 다 허용하고 결과를 보고 |
| Q-F4 | F | 모집글 소유자 open 상태에 접근 가능한 이름 `삭제` 버튼 + `window.confirm` → DELETE `/recruitments/{id}?revision=N`. closed 항목에는 삭제 버튼 없음 |
| Q-F5 | F | `로그아웃` 버튼이 보호 화면(390은 메뉴 열기 `button[aria-controls="campus-navigation"]` 이후 포함)에서 접근 가능한가 |
| Q-F6 | F | 로그아웃/미로그인 상태로 `/app/community` 이동 시 `가상 학번` 로그인 폼이 보이거나 `/app/login`으로 이동하는가 |
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
| `node --test "test/*.test.cjs"` | 19 pass / 0 fail |
| `node run.cjs` (env 없음) | `NOT_RUN` / `OPT_IN_MISSING`, stages 0, 네트워크·브라우저 없음 |
| 실제 2계정 브라우저 E2E (390/1280) | **NOT_RUN** — root 환경·DEMO 계정 미주입, F/A 계약 미병합 |
| `.github/workflows/p0-browser-harness-ci.yml` | 로컬 NOT_RUN, PR CI에서 확인 |

## 7. 남은 게이트
- F·A 브랜치 병합 후 Q-F1~F7, Q-A1~A3 확정 → 셀렉터 차이가 있으면 `tests/e2e/src/selectors.cjs`만 조정.
- root가 로컬 apps/web·API·DEMO seed를 띄우고 `P0_E2E_RUN=1`로 실제 실행 → 보고서 JSON을 검토. 실DB(MariaDB) 근거는 DB 게이트에서 별도로 판정.
- HTTP 보안 전수 검사(B), Lighthouse(TC-015)는 이 하네스 범위 밖.
