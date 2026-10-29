# TASK-P0-SECURITY-E2E — 승인된 로컬 서버 2계정 HTTP 검증기

- 상태: **TESTED (오프라인 HTTP 모의 회귀)**. 실제 HTTP·MariaDB·계정 생성·업무 CRUD는 **NOT_RUN**.
- 기준: `7f7eabbb44f09caeaac79798baab8a69485ab453`. 서버 통합 담당자가 추가하는 `/auth/me` 및 모집 논리 취소 DELETE 계약을 검사하며 서버를 구현하거나 활성화하지 않는다.
- 소유: `services/api/scripts/verify_p0_security.py`, `services/api/tests/test_p0_security_check.py`, 이 문서. 공통 인증·설정·DB·라우터·프런트는 변경하지 않는다.
- 관련 요구사항: FR-AUTH-001, FR-COM-001/004, FR-OPP-001/004, NFR-SEC-001~004, NFR-REL-001, TC-V1-COM-001/004, TC-V1-OPP-004. 상세 P0 계약은 [13_P0_SERVER_DB_RLS_CONTRACT.md](../v1-draft/13_P0_SERVER_DB_RLS_CONTRACT.md), 검증 원칙은 [08_TEST_QA.md](../08_TEST_QA.md)를 따른다.

## 1. 실행 전 게이트

기본 명령은 `NOT_RUN`을 출력하고 종료 코드 2로 끝난다. 승인 플래그 둘이 모두 `1`이 아니면 설정·비밀번호·HTTP 클라이언트를 읽거나 생성하지 않는다.

```powershell
# services/api/에서 실행. 기본은 연결·쓰기 없음.
uv run --locked python scripts/verify_p0_security.py
```

실행자는 별도로 승인된 가상 계정과 가동 중인 로컬 서버를 준비해야 한다. 이 검증기는 계정·DB·스키마·시드·서버를 만들지 않는다. 실제 실행은 root 운영자만 수행한다. PR 코드 병합 승인은 시드 생성·배포·운영 데이터 사용 승인이 아니다.

| 환경 변수 | 의미 |
| --- | --- |
| `DIT_API_RUN_P0_SECURITY_CHECK=1` | 로컬 HTTP 쓰기 검사 명시적 opt-in |
| `DIT_API_P0_SECURITY_CHECK_APPROVED=1` | 운영자의 해당 실행 승인 확인 |
| `DIT_API_P0_CHECK_BASE_URL` | 포트를 명시한 `localhost`, `127.0.0.1`, `[::1]` HTTP(S) origin만 허용 |
| `DIT_API_P0_CHECK_A_STUDENT_ID`, `DIT_API_P0_CHECK_B_STUDENT_ID` | 각각 `DITDEMO_A`, `DITDEMO_B`로 시작하는 승인된 합성 학번(최대 20자) |
| `DIT_API_P0_CHECK_A_PASSWORD`, `DIT_API_P0_CHECK_B_PASSWORD` | 외부에서 주입한 비밀값, argv·기본값·dotenv 없음 |
| `DIT_API_P0_CHECK_OPPORTUNITY_ID` | 승인된 DEMO 기회 UUID. 임의 공고 자동 선택 없음 |
| `DIT_API_P0_CHECK_OPPORTUNITY_MARKER` | 해당 공개 제목에 포함된 `DITNOW_DEMO_` + 8~60자 ASCII 식별자 |
| `DIT_API_P0_CHECK_CLOSE_SAMPLE=1` | 선택 사항: 별도 모집 샘플의 `open→closed` 검사. 아래 잔여 행 제한 확인 |

대상 origin에 사용자 정보·경로·쿼리·fragment·공백이 있으면 거부한다. `trust_env=False`, redirect 추종 금지, 요청별 5초 제한, 응답 본문 256KB 상한을 적용한다. HTTPS 인증서 검증을 끄지 않는다. 쿠키를 요청마다 비워 무인증 검사가 앞선 로그인 쿠키로 인증되지 않게 한다.

## 2. 실제 수행할 순서와 완료 조건

1. 서로 다른 가상 학생 두 계정 로그인 → `/auth/me`의 최소 DTO·DEMO·서로 다른 사용자/학과 확인. 무인증 개인·커뮤니티 조회는 401.
2. 주입된 기회 UUID의 공개 조회가 DEMO·제목 marker·정보 제공 전용인지 확인. 실제 DB 게시 상태 자체를 검증했다고 주장하지 않는다. 두 계정 모두 이 기회를 이미 저장했다면 기존 개인 행을 보존하고 쓰기 전에 중단한다.
3. 전교 익명 글 생성·동일 키 재생·다른 payload 충돌·조회·수정·이전 revision 충돌. B의 수정/삭제는 403/404, 무인증 수정/삭제는 401. 응답은 익명 필드 allowlist만 허용하며 알려진 사용자 UUID·학과·학번·토큰이 없어야 한다.
4. 실명 모집 생성·재생·조회·수정·이전 revision 충돌. B 수정/삭제/close와 무인증 수정/삭제를 거부해야 한다. 전교 조회는 정책상 가능하므로 다른 학과의 READ를 잘못된 접근이라고 판정하지 않는다.
5. 개인 기회 저장 자연 멱등성, 체크 항목 생성 키 재생, 수정·이전 If-Match 충돌, B의 타 소유자 수정/삭제 거부, A의 준비 상태·메모 변경과 B 목록 격리.
6. A logout → 이전 토큰 401 → 새 토큰 로그인 → 같은 내부 UUID 및 생성한 자료 재조회. 이것은 새 세션 HTTP 재조회 증거이며 서버 재시작/DB 영속성 증거는 아니다.
7. 이번 run에서 확인한 본인 ID만 marker·소유권을 재확인한 후 정리한다. 체크 삭제 tombstone 재생 409, 익명·모집 논리 삭제 이후 A/B 상세 404, 모집 공개 목록 부재와 생성 키 재생 404를 검사한다. 목록은 최대 500행만 확인하며 `has_more`가 계속 참이면 완전성을 주장하지 않는다.
8. 생성한 세션은 logout 후 이전 토큰 401로 확인한다.

`PASS_HTTP_SCOPE`는 위 HTTP 범위가 성공하고 모든 알려진 자원 정리가 검증된 경우만 출력한다. 전체 프로젝트는 항상 `overall_project=NOT_VERIFIED`다. 고정 단계/상태/개수만 출력하고 비밀번호·토큰·원문 응답·DSN·학생 UUID를 출력하지 않는다.

## 3. 삭제·실패·정리의 한계

- 익명: PATCH body revision, DELETE query revision. 모집도 같은 revision 계약이다. 개인 기회·체크 항목은 `If-Match`다.
- 모집 `DELETE ?revision=N`은 기존 cancel 서비스의 `open→cancelled` 및 `{id,deleted:true}` 응답이다. 원장·멱등 claim을 보존하는 **논리 취소**이며 물리 삭제가 아니다. 별도 `close`의 `open→closed`와 혼동하지 않는다.
- 기존 계약에서 `closed→cancelled`는 409다. 따라서 선택한 close 샘플은 닫힌 행이 남아 `NOT_VERIFIED_CLOSED_ROW_REMAINS`로 보고되고 전체 결과도 `NOT_VERIFIED`다. 검사기가 임의 상태 전이나 DB 삭제를 만들지 않는다. 기본 실행은 본인 close 성공 경로를 `NOT_RUN`으로 남긴다.
- 쓰기 응답이 끊기면 서버 생성 여부가 불명확할 수 있다. 알 수 없는 ID를 목록 전체에서 찾아 삭제하지 않으며 `unresolved_create_responses`를 보고하고 실패한다. marker/소유자가 바뀌어도 삭제하지 않는다.
- 예외·부분 실패 후에도 알려진 본인 자원과 세션 정리를 시도한다. 정리 실패는 `NOT_VERIFIED`이며 자동 재실행·대량 삭제·타인 자원 삭제가 없다. 운영자는 실패 보고 이후 별도 승인된 조사로 잔여 상태를 확인해야 한다.
- 소속/역할 변경·권한 회수·서버 재시작 영속성·물리 행 삭제·배포는 HTTP 검사만으로 증명하지 않으며 `not_run`에 남긴다. 직접 DB 변경·직원 권한 생성 기능은 없다.

## 4. 검증 증거

2026-10-30, Windows / Python 3.13 / uv 잠금 의존성:

- `uv run --locked pytest -q tests/test_p0_security_check.py`: **24 passed**. 실제 listener/network 없이 `httpx.MockTransport`만 사용.
- `uv run --locked ruff check scripts/verify_p0_security.py tests/test_p0_security_check.py`: **PASS**.
- 전체 API `uv run --locked pytest -q`: **1137 passed**, 기존 Starlette 테스트 클라이언트 deprecation 경고 1개. 전체 Ruff/format(186개 파일), OpenAPI snapshot 일치 검사 PASS. 프런트/공개 계약 변경은 없다.
- 저장소 `node scripts/check-agent-config.mjs` PASS(현재 경로 90/미러 skill 8), `node scripts/check-feature-progress.mjs` PASS(92개 기준선 보존), 문서 상대 링크 2개 존재 및 `git diff --check` PASS. NAV·공유 진행 보드는 root 단일 소유이므로 이 작업에서 편집하지 않는다.
- 회귀: 정상 전체 순서·재로그인·정리, 플래그 부재 시 클라이언트/설정 미생성, 외부 URL 거부, CLI 비밀값 정화, 익명 정보 누출·타 소유자 수정 허용·개인 목록 누출·오류 본문 비밀번호 echo 시 실패, marker 변경 시 삭제 거부, 불명확 생성 응답 시 대량 삭제 금지, 닫힌 모집 잔여 보고, 페이지 상한의 완전성 미주장, 외부 redirect·transport 예외의 고정 실패 출력, proxy/redirect 금지와 timeout 설정.
- 독립 Codex F 읽기 전용 리뷰: 원본 21개 직접 통과 후 비차단 비밀번호 echo 검사 권고를 수용했다. 최종 24개도 F가 직접 재실행하여 PASS, 현재 검사기 범위의 잔여 차단 finding 없음을 보고했다. AI 검토는 사람 승인·실HTTP 검증이 아니다.
- **NOT_RUN**: 실제 localhost HTTP, 실제 가상 계정 로그인, 실제 MariaDB P0 CRUD·권한 격리, 원격 DB·DDL·DML, 브라우저·배포. 모의 응답은 실제 서버의 보안 검증을 대신하지 않는다.
