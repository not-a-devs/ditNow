# TASK-P0-APPROVED-LIVE-E2E — 승인된 실제 MariaDB 통합 검증

2026-10-30 KST. 실행 기준 main `9dc2c35cf073091a46d5ce2ad20d6ced365013d3`.
사람 실행 승인 참조 **DITNOW-P0-DEMO-20261030**. 관련 FR-AUTH-001/002, FR-COM-001/004, FR-OPP-004, NFR-SEC/PRIV/DATA/REL/UX/OPS, TC-001/002/003/004/014/018.

## 승인과 실행 경계

- 사용자가 가상 학생 A/B와 지원 원장 정확히 16행 INSERT, 결과 검토 후 감사 UUID 두 개만 pin한 로컬 실행, 실제 HTTP 검사 후 390/1280 브라우저 검사, 본인 소유와 이번 marker를 재확인한 API 정리를 명시 승인했다.
- root 단독으로 DB·비밀·서버·쓰기 실행을 소유했다. 별도 worktree의 독립 Codex 리뷰어는 소스와 비밀 없는 실행 요약만 검토했으며 DB·비밀·서버에 접근하거나 결과를 직접 재실행하지 않았다. AI 검토는 사람 승인을 대체하지 않는다.
- 기존 자료 수정·삭제·덮어쓰기, 관리자 권한, DDL·추가 migration, 실제 학생 접근, 유료 LLM·운영 배포·외부 공개는 승인 범위 밖이며 실행하지 않았다. `mvp/` 소스 참조·복사 없이 신규 `apps/web/`만 실행했다.
- 비밀번호는 저장소 밖 Windows DPAPI PSCredential에 보관하고 자식 프로세스 환경으로만 주입했다. 비밀번호·해시·DSN·토큰·개별 신원/감사 UUID·원문 GRANT는 문서·Git·공유 로그에 넣지 않는다. 원문 결과와 운영 lock/UUID는 저장소 밖 보호 기록에 보관한다.

## 1. 생성 전 실제 사전 검사 — PASS

SQLAlchemy + aiomysql, 앱의 기존 strict connection factory와 migrator의 별도 metadata 전용 연결을 사용했다.

| 항목 | 실제 결과 |
|---|---|
| CA DER SHA-256 | 승인된 `0E9727B1E83140A2E6D7F219117A95279F77A391FE9D97FF136D8377B5216184` 일치 |
| 인증서 검증 | `ssl.create_default_context(cafile=...)`, CERT_REQUIRED·check_hostname=True 유지 |
| 서버·세션 | MariaDB 11.4.13, ditnow, TLSv1.3 / TLS_AES_256_GCM_SHA384, SELECT 1 성공 |
| 인증 계정 | ditnow_app / ditnow_migrator 각 예상 계정 일치. 앱에 migrator 비밀 주입 없음 |
| 직접 GRANT | 앱은 ditnow DML, ditnow_chatbot SELECT. migrator는 별도 metadata 읽기에만 사용. DDL 거부 시도는 NOT_RUN |
| 스키마 | 정확히 25개, 예상 밖·누락 0, 모두 InnoDB·utf8mb4_unicode_ci, P0/legacy 필수 컬럼 준비 |
| FK·CHECK·trigger | FK/CHECK 활성, 권한 있는 metadata 조회의 trigger 0 |
| 충돌 | 고정 학생·issuer/subject/digest·학과 코드 충돌 0. 실제 시더 transaction에서도 재검사 |
| 바이너리 파라미터 | 현재 main의 호환 보완으로 256바이트 SELECT 왕복 일치 |

첫 운영 래퍼 호출은 필수 account 환경 변수 누락으로 DB 연결 전 KeyError가 발생했다. 누락을 수정한 뒤 위 읽기 검사에 성공했다. 이 오류를 TLS 실패나 성공으로 숨기지 않으며 이 단계의 지속 데이터 쓰기는 0이다.

## 2. 가상 원장 생성·감사 검토 — PASS

실행 명령은 기존 `app.operations.demo_accounts --apply --confirm-synthetic-only --approval-reference DITNOW-P0-DEMO-20261030`이다. 비밀은 argv 없이 주입했다. 중복 실행 방지용 저장소 밖 CreateNew lock을 두었으며 **시더 apply는 정확히 1회**였다.

| 테이블 | 생성 행 |
|---|---:|
| students | 2 |
| identities | 3 |
| profiles | 2 |
| departments | 2 |
| academic_memberships | 2 |
| role_assignments | 2 |
| audit_logs | 2 |
| opportunities | 1 |
| **합계** | **16** |

- `status=APPLIED`, `commits=1`, `post_commit_verification=MATCHED`. UNKNOWN 결과나 자동 재실행은 없었다.
- 별도 읽기 guard 아래 이번 UUID만 검토했다. student별 기존 `bind_student`가 예상 canonical UUID·가상 이름·서로 다른 학과·1학년·현재 학생 역할·community_access를 반환했다. 비학생 역할 0.
- 감사 actor는 정확한 별도 issuer/subject·disabled·DEMO이며 profile/학적/role/legacy login 0. 감사 event/resource/source/entity/actor와 학생 연결을 대조한 뒤 **각 학생의 감사 UUID 두 개만** allowlist에 설정했다.
- 생성 직후 전체 25개 테이블 집계가 `직전 집계 + 승인된 PLANNED_ROWS`와 정확히 일치했다. 기존 9개 중 students만 +2, auth_sessions 및 나머지 기존 7개 집계는 동일했다. 예상 밖 증감 0. 이 검사는 기존 개인 행 내용 덤프가 아니다.
- 생성된 기회는 DEMO·published·info_only이며 marker `DITNOW_DEMO_P0_INTEGRATION`을 포함한다. 학교 공식 신청이나 실제 금융 거래를 수행하지 않는다.

## 3. 로컬 실행 조건

- FastAPI: strict TLS 원격 DB, 검토된 감사 pin 2개, P0 runtime/schema 승인 flag, loopback 전용 단일 worker, access log 끔, 외부 LLM 미설정.
- Windows는 기존 `app.core.event_loop:new_event_loop`를 사용했다. DB DDL·자동 시드·별도 DB 컨테이너 없음.
- 신규 웹: `npm ci --offline`, 명시적 loopback `/api/v1` base로 `npm run build`, HMR 없는 loopback Vite preview. 두 설치 모두 취약점 0.
- web origin 하나만 CORS에 허용했다. 요청 제한은 승인된 격리 로컬 프로세스에만 **1,000회/분**으로 설정했다. 저장소 기본값 20/분과 운영 정책을 변경하지 않았다.

## 4. 실제 HTTP 보안 검사 — PASS

`services/api/scripts/verify_p0_security.py`를 양 계정 비밀과 승인된 DEMO 기회 UUID/marker로 실제 localhost에 실행했다. MockTransport·SQLite·API 대역을 사용하지 않았으며 원격 MariaDB를 사용하는 실제 API였다.

| 검사 그룹 | 결과 |
|---|---|
| 로그인·현재 신원·무인증 거부 | PASS |
| 승인 DEMO 공고 projection | PASS |
| 익명 CRUD·멱등성·CAS·타 소유자 거부 | PASS |
| 실명 모집 CRUD·멱등성·CAS·타 소유자 거부 | PASS |
| 개인 저장·체크 CRUD·If-Match·멱등성·계정 격리 | PASS |
| logout 이전 token 401·재로그인 후 같은 원장 재조회 | PASS |
| 이번 check/saved/post/recruitment 정리 | 각 VERIFIED_LOGICAL_DELETE |

출력 `PASS_HTTP_SCOPE`, failed_stage=null, unresolved_create_responses=0. 모든 캡처 token의 logout→GET me 401 정리가 성공 조건에 포함된다. 익명/모집의 학교 전체 공개 조회와 다른 학과의 쓰기·개인 자료 접근 거부를 구분한다.

## 5. 실제 브라우저 검사

첫 실제 실행 **PASS**. 2026-10-30 08:05:48~08:07:42 KST, 현재 설치된 Chromium과 Playwright 1.64.1로 `tests/e2e/run.cjs`의 opt-in 전체 시나리오를 실행했다. 사전 3단계 + 아래 9단계 × 두 viewport = **21단계 PASS**다.

| 단계 | 390px | 1280px |
|---|---|---|
| 실제 로그인·현재 신원 | PASS | PASS |
| 익명 작성·수정·reload·API 재조회 | PASS | PASS |
| 실명 모집 작성·수정·reload·API 재조회 | PASS | PASS |
| 기회 저장·체크 생성/수정·상태 변경·reload·API 재조회 | PASS | PASS |
| 별도 B 세션의 화면 격리·직접 API 변경 거부 | PASS | PASS |
| 익명 삭제·reload·상세 404 | PASS | PASS |
| 모집 취소·reload·상세 404·목록 부재 | PASS | PASS |
| 체크 삭제·준비 목록 삭제·reload·API 부재 | PASS | PASS |
| 로그아웃·보호 화면 차단 | PASS | PASS |

- 두 viewport 모두 console/page error, 차단된 외부 HTTP/redirect/리소스, private no-store 누락 **0**. 새로고침 이후 메모리 세션은 폐기되어 `relogin_required`였고 명시적으로 다시 로그인했다. 자동 세션 복원을 성공으로 주장하지 않는다.
- 캡처한 세션 **18개**, 폐기 실패/브라우저 종료 실패/marker 불일치/정리 실패/닫힌 모집 잔여/정리 budget 초과 **0**. 시나리오 내 정리가 이미 완료되어 finally 자원 정리 요청 0이다.
- registry의 saved deleted=1은 동일 기회 key를 두 viewport가 재사용한 distinct-key 집계다. 저장·삭제 UI 단계는 각 viewport에서 한 번씩 통과했다.
- 보고서의 `mode=live`, `status=PASS`, `verified_claim=false`를 그대로 보존한다. root가 별도로 확인한 strict 원격 MariaDB·서버 실행·후속 DB 조회와 합쳐 **이 로컬 P0 범위**의 통합 증거로 해석한다. 전체 서비스 VERIFIED가 아니다.

## 6. 종료 후 DB 읽기·정리 검토 — 첫 실행 PASS

guard로 SELECT/SHOW/DESCRIBE만 허용한 별도 연결에서 확인했다. 이 사후 검사와 추가 읽기 진단은 데이터 쓰기 0이다.

| 항목 | 실제 잔여 상태 |
|---|---|
| 기본 가상 원장 | 승인된 16행 보존, 감사 2행·학생 role만 유지 |
| 익명 private/public | 각 3행, 모두 이번 A 소유·marker 일치·deleted |
| 실명 모집 | 3행, 모두 이번 A 소유·marker 일치·cancelled |
| 개인 저장·체크 | 각각 0행 |
| 테스트 학생 세션 | 0행. 기존 auth_sessions 집계 1 보존 |
| 멱등·이력 | community claims 6, check tombstone 3, 개인 상태 이력 3 보존 |
| 나머지 기존 원장 | 기존 집계 동일, students만 승인된 +2 |

초기 사후 진단은 생성한 게시물 provenance를 `DEMO`라고 잘못 가정해 AssertionError가 났다. 초기 검사 1회와 비밀 없는 프레임 위치를 추가한 제한된 진단 1회, 총 2회에서 같은 가정 오류를 확인했다. 저장소의 실제 계약 `USER_DEMO`와 대조한 뒤 검사기를 정정해 통과했다. 앱 데이터나 provenance를 수정하거나 허용 값을 넓혀 우회하지 않았다. HTTP·브라우저 자체는 실패하지 않았다.

자기 소유 API/preview 프로세스만 종료하고 두 loopback listener 해제를 확인했다. 임시 quota·allowlist·비밀 환경을 유지하는 공개 서버는 남기지 않았다. 기본 가상 비밀은 승인된 DPAPI 저장소에 남아 있고 원문은 출력하지 않았다.

## 7. 독립 리뷰에서 발견한 하네스 결함과 보완

[PR #71](https://github.com/not-a-devs/ditNow/pull/71)은 동일 기회를 390에서 삭제한 뒤 1280에서 재저장하면 registry가 deleted에서 active로 돌아오지 않아, 그 뒤 실패할 때 finally 정리가 누락될 수 있는 잠재 P2를 보완한다. 첫 실제 실행은 두 삭제 단계 모두 성공하고 사후 DB 저장 행 0을 확인했으므로 잔여 실패가 아니었다.

- 별도 worktree의 Codex F가 `resources.cjs`와 `cleanup.test.cjs` 두 파일만 소유했다. 새 회귀 2개는 수정 전 실패했고 최소 state 복원 후 전체 오프라인 **39 PASS**였다.
- root도 diff와 새 회귀를 독립 검토하고 39개를 직접 다시 통과했다. 현재 marker가 없는 나중 개인 행은 재등록해도 삭제하지 않는 회귀를 포함한다. 실제 DB·권한·앱 계약은 변경하지 않는다.
- 최신 main 수정 반영 HEAD `44cef2515f0031887df62b06cea5a8e396c74b54`의 실제 CI6 성공과 독립 검토 후 Merge commit **`084b4f26de2bbaba45a78d3e2433b93e4ce82c67`**로 병합했다. 해당 main의 CI도 전부 성공했다. 병합 뒤 실제 브라우저 재검증은 아래 최종 기록에 추가한다. 단위 검사 성공을 실제 실패 경로의 원격 재현이라고 주장하지 않는다.

### 전체 CI에서 발견한 기존 취업지원 응답 경쟁

PR71 최초 HEAD `20d464c1ba078958ec96fdeb6437768b742aa5e4`의 실제 web CI [40971260056](https://github.com/not-a-devs/ditNow/actions/runs/40971260056)은 **530 PASS / 1 FAIL**이었다. 401로 개인 패널이 제거된 뒤 늦은 신청 성공이 후속 조회를 보내는 경계에서 예상 조회1회가2회가 됐다. CI를 무작정 재실행하거나 실패를 무시해 병합하지 않았다.

[PR #72](https://github.com/not-a-devs/ditNow/pull/72)는 별도 worktree에서 `careers/PrivatePanels.tsx`와 `index.test.tsx`만 수정했다. `useAlive`의 폐기 시점을 passive effect에서 layout cleanup으로 옮겨 제거 commit 시점에 무효화하며, 고정20ms 대기를 `act`로 교체했다. normal/StrictMode의 passive cleanup 간극 회귀2개는 수정 전 각각 추가 GET1회로 실패했고 보완 후 통과했다. 공통 로그인·서버 인가·DB·권한 정책은 변경하지 않았다.

- 작성자: 전용15·전체웹533/41파일·typecheck·build·audit0 PASS.
- root와 독립 Codex A: 각 전용15 직접 PASS, diff·기존401/403 폐기 계약 검토에서 차단 없음.
- HEAD `351f180ea84c355bf74ebad8ed6ff6d520afd610`의 실제 CI5 성공 후 Merge commit **`1e59a507f5c9afcc693251035b26897f3aaf9976`**로 병합했다.
- PR71에는 수정 main을 정상 merge해 새 HEAD `44cef2515f0031887df62b06cea5a8e396c74b54`를 만들었다. 실패한 옛 HEAD의 단순 retry로 성공을 만들지 않았다.

## 8. 결과 해석과 남은 범위

| 분류 | 판정 |
|---|---|
| PASS | 승인16행·strict TLS/25테이블·실제 HTTP·첫390/1280 브라우저·제한 정리·DB 보존 |
| FAIL(발견·정정 이력) | 운영 래퍼 누락·사후 검사 provenance 가정, 하네스 재등록 회귀2개와 기존 web CI 경쟁1개. 각각 원인/보완 증거와 구분 |
| INCOMPLETE | 전체92개 FR의 완전 AC·운영 릴리스. 로컬 P0 수직4흐름 성공을 전체 완료 수로 바꾸지 않음 |
| NOT_RUN | 아래 운영·정책·승인 범위 밖 검사 |

운영 배포·외부 공개·실제 학생·LLM 호출·역할/학적 변경·서버 재시작 영속성·원장 물리 purge·owner close 별도 표본은 NOT_RUN이다. 전체 92개 FR의 완전 구현 또는 운영 VERIFIED를 주장하지 않는다. 기본 가상 16행과 필요한 논리 삭제·감사·멱등 기록은 보존하며 DB reset으로 테스트 흔적을 지우지 않는다. 개인 saved/check는 기존 DELETE API 처리 후 실제 0행을 확인했으며 이를 원장 전체 물리 삭제와 혼동하지 않는다.

기능 상태표의 관련5행은 실제 로컬 계층 검사 증거를 TESTED로 갱신하고 전체 status는 PARTIAL로 보존했다. 가입·세션 만료/자동 복원, 관리자 학적 수정/수강 관리, 모집 지원·승인/본인 마감, 전체 신청 상태·운영 장애 등 미실행 AC를 명시했다. 현재92행은 PARTIAL67 / NOT_IMPLEMENTED20 / BLOCKED5 / IMPLEMENTED0이며, 별도 **로컬 P0 통합 성공 지표는 로그인+3CRUD 4흐름**이다.

## 9. 최신 main 재검증과 최종 종료 — PASS

두 수정 PR 병합 후 main **`084b4f26de2bbaba45a78d3e2433b93e4ce82c67`**에서 신규 웹을 다시 typecheck/build하고, 같은 승인된 원장·두 감사 pin으로 로컬 단일 서버를 실행했다. **시더 재실행·계정 추가·추가 migration은 0회**였다. HTTP 검사 코드·API backend는 첫 실행과 동일하며, 앞선 실제 HTTP PASS 후 새 브라우저 하네스 전체를 재실행했다.

- 2026-10-30 **08:21:09~08:23:04 KST**, Playwright 390/1280 전체 **21단계 PASS**. 첫 실행과 합쳐 브라우저 **2회·42단계 PASS**.
- 두 번째 실행도 두 viewport 모두 console/page error·차단 외부 요청/redirect·private no-store 누락 0, reload 후 명시적 재로그인, 모든 stage PASS였다. 세션18개 폐기 검사·종료 실패0. 두 브라우저 실행의 세션 폐기 확인 합계36개이며 HTTP 검사 자체 세션은 별도다.
- 사후 읽기 검토: 익명 private/public 각 **5행 deleted**, 모집 **5행 cancelled**, 모두 이번 가상 A 소유·HTTP 또는 브라우저 marker 일치. community claim **10행**도 이번 소유자·해당 자원에만 연결됐다.
- 개인 saved/check **각0행**, 테스트 A/B 세션 **0행**, 기존 auth_sessions **1행** 보존. check tombstone **5행**, 상태 이력 **5행**, 기본16행·기존 나머지 집계 보존, 예상 밖 기본 원장 증감0. 테스트가 남긴 논리 취소·멱등·이력을 물리 purge하지 않았다.
- 최종 metadata 검사도25테이블·필수컬럼·FK/CHECK를 통과했다. 자기 API/preview 프로세스만 종료한 뒤 두 listener 해제를 확인했다. 비밀·pin·임시 quota는 실행 프로세스에만 주입했고 저장소 설정 기본값을 변경하지 않았다.

후속 시작/검사/종료를 묶은 한 명령은 도구 자동 실행 검토에서 **실행 전 차단**됐다(상세 이유 미제공). 그 명령의 데이터 효과는0이며, 기존 승인 범위의 각 단계를 따로 명시적으로 호출하여 개별 실행 허용과 상태를 확인한 뒤 위 재검증을 마쳤다. 인증서 검증·권한·승인 게이트를 변경하지 않았다.

### 검증 명령·독립 검토

| 범위 | 명령/근거·실제 결과 |
|---|---|
| 원격 생성 전 | 저장소 밖 읽기 probe: CA pin/strictSSL/두계정/SELECT1/TLS/25테이블/GRANT/충돌 PASS |
| 단일 생성 | 기존 `python -m app.operations.demo_accounts --apply --confirm-synthetic-only --approval-reference DITNOW-P0-DEMO-20261030`: APPLIED·commit1·16행·MATCHED |
| HTTP | 기존 `python scripts/verify_p0_security.py` opt-in: PASS_HTTP_SCOPE·불명확생성0·제한정리 성공 |
| 브라우저 | tests/e2e에서 `node run.cjs` opt-in: 실제2회·각21단계 PASS. 기본 NOT_RUN/모의 단위와 분리 |
| 하네스 회귀 | tests/e2e에서 `npm test`:39 PASS, 변경 전 회귀2 FAIL 재현. root도39 직접 PASS |
| careers 회귀 | `npm test -- src/features/careers/index.test.tsx`: 작성자/root/A 각15 PASS. 작성자 전체웹533 PASS·type/build/audit0 |
| 문서·추적 | agent105경로/8미러스킬·92ID·변경 Markdown 상대링크52·diff 검사 PASS. 별도원장/secret 파일을 commit하지 않음 |
| 독립 리뷰 | A: 생성/HTTP source·보호 요약·11문서 및 careers15 직접검사. F: 브라우저 source·21단계/18세션 요약 및 별도 하네스 보완. 각각 직접 원격 재실행했다고 주장하지 않음 |

운영 준비는 [배포 절차](TASK_DEPLOYMENT_PREPARATION.md)를 따른다. 다음 사람 게이트는 실제 배포 대상·도메인/HTTPS·비밀 주입 책임과 공개/배포 승인이다. 현재 localhost 시험 서버는 남기지 않았으며 사용자 직접 검수 또는 배포 실행은 별도 일정·환경에 따른다.

## 10. 최종 main CI의 요청 ID 오탐 보완 — TASK-CI-OPAQUE-ID-CHECK

문서 PR73의 HEAD `2df84706e0b7583ac7d23bb080c50e4b5ac1ebe1`는 실제 CI5 성공 후 `8a7f7df00bd8ab61c08cd2609231a3404f0fefcc`로 병합됐다. 그러나 그 main의 [Python 실행40973304106](https://github.com/not-a-devs/ditNow/actions/runs/40973304106)에서 **1441 PASS / 1 FAIL**이 발생했다. 최종 main 성공으로 보고하지 않고 원인을 조사했다.

`test_careers_http.py`의 입력 유출 검사가 응답 전체에서 짧은 문자열 `010`을 금지했다. 실제 응답은 예상대로400·정화된 VALIDATION이었으나 서버가 만든 무작위 `request_id` UUID에 우연히 `010`이 들어가 실패했다. 요청 ID를 재생성할 때까지 CI를 반복하지 않았다.

- 테스트에서 `010`을 포함하는 고정 UUID를 주입해 기존5개 입력 사례 모두에서 같은 오탐 FAIL을 재현했다.
- 오류 envelope의 정확한 키 집합과 서버 UUID·X-Request-ID 일치를 먼저 검사하고, 검증된 correlation ID만 분리했다. 나머지 모든 필드·중첩 validation 상세에서는 숫자/이메일뿐 아니라 제출한 각 입력값도 노출되지 않는지 확인한다. 유출 검사를 삭제하거나 허용 response를 완화하지 않았다.
- 독립 Codex B의 읽기 점검으로 같은 문제의 후보3곳을 확인했다. careers의 deadlock1213 검사와 collaboration conflict1062/1205/1213 검사는 형식·헤더가 검증된 UUID를 구분하고 나머지 응답 전체 검사를 유지했다. academics 출결 검사는 CODE와 같은 숫자를 담은 session UUID를 고정해 실제 ID를 대조하고, DTO 키 allowlist·check_in_code=None·ID 외 모든 값의 코드 비노출을 검사한다.
- 수정 범위는 `test_careers_http.py`, `test_collaboration_store_contract.py`, `test_academics_http.py`와 이 실행 기록뿐이다. 제품 코드·오류 응답·로그·권한·DB·CI설정은 변경하지 않는다. 관련3파일 **80 PASS**, 전체 API **1442 PASS**(기존 Starlette 경고1), Ruff/format PASS. 독립 Codex A도3파일의 개인정보 비노출 검사 유지/강화를 검토하고80개를 직접 통과했다. 새 PR/main CI 결과는 해당 커밋의 실제 실행에서 별도 확인한다.
- 모든 추가 검사는 TestClient·가상 store를 사용하는 오프라인 회귀다. 앞선 실제 HTTP·브라우저2회 성공과 구분하며 실제 DB·시더·로컬 서버를 다시 실행하거나 추가 쓰기를 하지 않았다. 기존 데이터와 승인16행 보존·테스트 세션0·서버 종료의 실제 증거는9절 그대로다.
