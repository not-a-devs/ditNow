# TASK-LIVE-E2E-PREFLIGHT — MariaDB 재검증과 실행 승인 대기

2026-10-30 KST. 기준 main `f8705eac26dc12960b2689e894497e9893371ca5`. 관련 FR-AUTH-001/002, FR-COM-001/004, FR-OPP-004, NFR-SEC/PRIV/REL/OPS 및 기존 P0 TC를 유지한다. 이번 검사는 원격 **읽기 전용**이며 실제 가상 계정 생성·업무 CRUD 쓰기·운영 배포는 실행하지 않았다.

## 1. 실제 DB 읽기 결과

root가 승인된 저장소 밖 DPAPI 자격을 검사 자식 프로세스에만 주입했다. 검사 후 환경에서 제거했고 비밀번호·DSN·원문 GRANT·개인 행 값은 출력하지 않았다. 모든 데이터 문장은 SELECT/SHOW였고 세션의 문자셋·READ ONLY 설정만 사용했다. DDL·지속 데이터 쓰기 0이다.

| 검사 | 실제 결과 |
|---|---|
| CA 인증서 DER SHA-256 | `0E9727B1E83140A2E6D7F219117A95279F77A391FE9D97FF136D8377B5216184` 일치 |
| CA·호스트 검증 | ssl.create_default_context(cafile=...), CERT_REQUIRED·check_hostname=True 유지 |
| migrator 읽기 연결 | SQLAlchemy+aiomysql의 connect_args ssl context, 명시적 ditnow_migrator로 성공 |
| 앱 읽기 연결 | 현재 기반의 엄격 create_database_engine, ditnow_app 인증 성공 |
| 버전·DB·세션 | MariaDB 11.4.13 / ditnow / TLSv1.3 / TLS_AES_256_GCM_SHA384 |
| SELECT 1·계정 일치 | 두 계정 모두 PASS. 인증 계정의 host 부분은 비공개 |
| 스키마 | 예상 25개와 정확 일치, 누락·추가 0, 모두 InnoDB·utf8mb4_unicode_ci |
| P0 16개 테이블·필수 열 | 누락 0 |
| FK·CHECK 세션 설정 | 모두 활성(1). 전체 제약 정의의 업무 적합성·오류 주입 시험과 구분 |
| 스키마 트리거 | 별도 migrator 메타데이터 조회에서 0 |
| 앱 직접 GRANT | ditnow의 SELECT/INSERT/UPDATE/DELETE, ditnow_chatbot의 SELECT, 직접 DDL 권한 없음 |
| migrator 직접 GRANT | 두 DB의 ALL PRIVILEGES. 앱 런타임에는 주입하지 않음 |
| 기존 집계·P0 초기 상태 | 아래 표와 일치. 기존 행 수정·개인 행 값 조회 0 |

| 기존 테이블 | 이번 집계 |
|---|---|
| students / auth_sessions | 3 / 1 |
| courses / course_sessions | 42 / 8 |
| enrollments / exams | 61 / 13 |
| graduation_rules / graduation_rule_categories | 2 / 4 |
| question_logs | 0 |

이 값은 이전 root 검사 집계와 같았다. 새 P0 테이블 16개의 행 수는 모두 0이었다. 계정과 개인 데이터의 진위를 추정하거나 기존 세션·학생 행을 가상 계정으로 채택하지 않는다.

## 2. 실제 조회에서 발견한 차단과 보완

main 기반의 TLS·메타데이터 준비 검사는 성공했지만, 가상 키 충돌 조회에서 identities.binding_digest의 바이트 파라미터가 `TypeError: 'str' object is not callable`로 실패했다. 인증서 오류가 아니다. 동일 실패를 반복하지 않고 안전한 프레임 이름·행 번호와 설치된 드라이버 소스로 원인을 분리했다.

- 잠금 버전은 aiomysql 0.3.2·PyMySQL 1.2.3이다. aiomysql은 bytes에서 내부 escape_bytes_prefixed를 호출하지만, 설치된 PyMySQL은 그 이름을 import 호환용 문자열로 제공한다.
- [PyMySQL 변경 기록](https://github.com/PyMySQL/PyMySQL/blob/main/CHANGELOG.md)과 [상류 이슈 #1274](https://github.com/PyMySQL/PyMySQL/issues/1274)는 내부 변환 함수의 비공개 계약과 호환 문제를 설명한다(확인 2026-10-30). [현재 변환 소스](https://github.com/PyMySQL/PyMySQL/blob/main/pymysql/converters.py)와 설치 소스를 대조했다.
- 과거 버전으로 내리지 않았다. 보안 수정이 포함된 1.2.3을 유지하고 API 요구 범위를 `>=1.2.3,<1.3`으로 제한했다. 설치되는 버전 자체는 변경되지 않았다.
- 엄격 연결 클래스에서 bytes/bytearray만 `X'hex'` 이진 리터럴로 직렬화한다. PyMySQL 1.2.3 Connection.escape가 사용하는 형태이며 converters의 `_binary X'hex'`와 문자열이 동일하다고 주장하지 않는다. 값은 hex 알파벳으로만 구성되고 문자셋·NO_BACKSLASH_ESCAPES에 의존하지 않는다. 다른 타입은 기존 aiomysql 처리에 맡긴다.
- 글로벌 드라이버 패치·TLS 완화·원장 타입/스키마·신원/권한 정책 변경은 없다. 독립 Codex가 해당 경계를 읽기 검토하고 전용 15개를 직접 통과했다.

### 보완 검증

| 범위 | 결과 |
|---|---|
| 보완 전 새 오프라인 회귀 | 10 FAIL / 5 PASS — 실제 잠금 드라이버로 재현 |
| 보완 후 전용 회귀 | 15 PASS: 빈 bytes·전체 256값·인용부호/역슬래시·합성 신원 해시·bytearray·두 SQL 모드·기존 타입 |
| 전용 + DB 설정 + 계정 도구 | 75 PASS |
| 보완 후 전체 API | 1442 PASS, 기존 Starlette 테스트 클라이언트 deprecation 경고 1개 |
| 정적·계약·탐색 검사 | Ruff·포맷 231파일·OpenAPI 스냅샷·agent 100경로/8skill·92개 기능 추적·diff PASS |
| 보완 브랜치의 실제 엄격 TLS 읽기 | PASS, 모든 256 바이트의 파라미터 SELECT 왕복 일치 |
| 보완 브랜치의 계정 도구 메타데이터 검사 | PASS, 현재 25개 준비 상태와 FK/CHECK 확인 |
| 보완 브랜치의 합성 키 충돌 SELECT | 충돌 종류 빈 목록. 이 시점의 결과이며 실제 생성 직전 재검사 필수 |
| 원격 쓰기·생성 | NOT_RUN, 0 |

보완 브랜치의 실제 읽기 성공과 기준 main의 원래 실패를 구분한다. 리뷰·CI·병합 후 실행 커밋을 고정하며, 이 결과를 가상 계정 생성·HTTP·브라우저 E2E 성공으로 승격하지 않는다.

## 3. 계정 생성 승인 범위

[기존 생성 도구](TASK_DEMO_ACCOUNT_OPS.md)의 단일 commit은 신규 16행이다. 학생 A/B의 legacy 로그인 2개, canonical identities 2개와 disabled 감사 신원 1개, profiles/departments/학적/student 역할 각 2개, 승인 감사 2개, DEMO info_only 기회 1개다. 상세 승인 체크리스트는 별도 계정 승인 작업에서 작성한다.

승인 전에 이 도구의 apply, 계정 비밀번호 생성·영구 보관, audit allowlist pin을 통한 로컬 업무 활성화를 실행하지 않는다. 승인 이후에도 고정 학생·issuer/subject·학과 코드 충돌은 무변경 중단이며 기존 자료 채택·덮어쓰기·비밀번호 초기화를 하지 않는다. commit 결과 UNKNOWN/YES 실패는 자동 재실행하지 않는다.

audit UUID allowlist는 성공 결과의 **승인 감사 2개 UUID**를 운영자가 대조해 주입하는 JSON 목록이다. 학생 UUID나 감사 전용 actor UUID를 대신 넣지 않는다. 기본 빈 목록으로는 업무 권한이 생기지 않는다. 실제 생성 전까지 이 목록도 비워 둔다.

## 4. 기능별 실제 실행 상태

| 기능 | 생성 | 조회 | 수정 | 삭제/취소 | 재로그인 | 두 계정 격리 |
|---|---|---|---|---|---|---|
| 공통 로그인·현재 UUID/권한 | NOT_RUN | NOT_RUN | 해당 없음 | NOT_RUN(로그아웃) | NOT_RUN | NOT_RUN |
| 익명 게시글 | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| 실명 모집 | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN(논리 취소) | NOT_RUN | NOT_RUN |
| 개인 기회·체크 준비 | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

모두 실제 계정 생성·연결 승인 대기다. [HTTP 검사](TASK_P0_SECURITY_E2E.md)의 모의 24개와 [브라우저 하네스](TASK_P0_BROWSER_E2E.md)의 오프라인 37개 성공은 위 표를 PASS로 바꾸지 않는다. 전교 공개 커뮤니티의 다른 학과 조회는 기존 정책상 허용되며, 소유자 쓰기·개인 목록·현재 학적 권한 격리를 별도로 검사한다.

## 5. 승인 대기 중 병렬 진행

- 계정 승인 범위·충돌·실패 처리·audit allowlist 절차를 한 문서로 검토한다.
- 비밀값/원격 DB 없는 신규 앱과 비활성 FastAPI의 로컬 503·CORS·비공개 캐시·화면 경계를 실제 검사한다.
- 공개 URL·호스팅·도메인·HTTPS·서버 프로세스·프록시 신뢰·CORS·비밀 주입·재시작 절차를 준비하며 운영 배포는 실행하지 않는다.
- 실제 HTTP/브라우저 검증은 loopback 전용으로 수행한다. 테스트 전용 요청 한도나 pacing을 명시적으로 승인·설정하며 429를 무시하거나 자동 운영 한도 완화로 통과시키지 않는다. 선택적 close 표본은 잔여 closed 행이 남으므로 별도 승인 전 제외한다.
