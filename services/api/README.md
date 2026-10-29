# DIT NOW FastAPI 기반

**최신 실제 검증(2026-10-30):** 승인 `DITNOW-P0-DEMO-20261030`으로 공통 로그인·현재 canonical 신원·익명 글·실명 모집·개인 준비의 실제 HTTP 및 신규 웹 390/1280 E2E를 strict TLS 원격 MariaDB에서 통과했다. [실행 SHA·범위·정리 증거](../../docs/dev-prep/TASK_P0_APPROVED_LIVE_E2E.md)를 따른다. 아래 TASK-B/F/DB-CONFIG의 미연결·승인 대기 서술은 당시 작업 기록이다. 현재는 검토한 감사 pin·P0 runtime/schema flag·DIT_API_DB_*를 모두 갖춘 경우에만 strict engine을 실제 보호 라우터에 연결하며 기본은 차단한다. 개인 학적 RAG·외부 LLM·운영 배포는 이번 검증에 포함하지 않았다.

TASK-B · NFR-SEC-004/005, NFR-PRIV-003, NFR-REL-004, NFR-OPS-001/002의 기반 코드다. 공개 `/health`, `/api/v1/health`는 프로세스 생존만 확인한다. 인증·DB·학생 CRUD는 아직 구현되지 않았으며 DB 준비 성공으로 표시하지 않는다. 최종 프런트는 별도 신규 앱이며 `mvp/`는 사전 프로토타입으로 보존하고 최종 서비스·시연·제출에서 제외한다. 해당 코드를 새 앱에 복사하지 않는다.

TASK-F는 [기존 챗봇](../../chatbot/README.md)의 검색기를 통합 API의 `GET /api/v1/ai/campus/search`에 연결한다. 시설 스냅샷 검색만 제공하며 별도 시연 로그인·관리자 API·학생 DB·LLM을 실행하지 않는다. 검색 결과의 공식 출처·최신성은 UNKNOWN이며 개인정보 질문과 전체 AI 브리핑의 완료를 뜻하지 않는다.

## 학번 로그인과 AI 답변 (DEC-020)

챗봇의 의도 분류·후속 질문·개인 질문 계산·LLM 답변을 패키지 함수 그대로 호출한다(복제 없음). 학생·학적은 가상(DEMO) 데이터다.

| 경로 | 설명 |
| --- | --- |
| `POST /api/v1/auth/login` | 테스트 환경의 격리 메모리 DB에서만 가상 토큰 회귀 검사. 실서버는 공통 신원 bridge 승인 전 503 |
| `POST /api/v1/auth/logout` | 동일 경계에서 가상 토큰 폐기; 실서버 503 |
| `POST /api/v1/ai/ask` | `{question, history?}` + 선택 `Authorization: Bearer`. 교내 질문은 비로그인 허용, 개인 질문은 로그인 필요(`need_login`) |

설정(`DIT_API_` 환경 변수): `DATABASE_URL`은 legacy 호환 키이며 운영 연결을 활성화하지 않는다. `ENVIRONMENT=test`와 정확한 `sqlite+aiosqlite:///:memory:` 조합에서만 격리 회귀용 DB를 생성한다. 그 외 환경·URL에서 로그인·토큰을 제공한 개인 질문은 503이며 `/health`와 비로그인 공개 조회를 유지한다. `LLM_PROVIDER`·`LLM_MODEL`·`LLM_API_KEY`·`LLM_BASE_URL`은 답변 생성 설정(없으면 `/ai/ask` 503), `CURRENT_SEMESTER`, `ASK_RATE_LIMIT_PER_MIN`은 시연 학기·IP 요청 제한 설정이다.

서버 시작 시 테이블·시드를 만들지 않는다. `app.seed_demo`도 정확한 격리 메모리 DB 이외의 대상은 연결 전에 거부한다. 원격 DB가 비어 있다고 추정하거나 legacy `students`·`auth_sessions`를 플랫폼에 생성하는 명령이 아니다. DEC-020의 학번 로그인 및 명시적 시드 방향은 유지하되, 공통 UUID·현재 계정/학적 검증 bridge와 승인된 migration 소유자의 대상·버전·최소 권한·엄격 TLS 확인은 후속 승인 게이트다. 앱 설정에 migration 계정 비밀값을 넣어 실행하지 않는다.

`/auth/*`, `/ai/ask` 경로 트리의 성공·검증 실패·인증 실패·요청 제한·내부 오류·404·후행 슬래시 응답은 `Cache-Control: private, no-store`다. ASGI `root_path`(프록시 접두사·mount)를 뺀 route 기준 경로로 판정한다. AI 요청 제한은 토큰 DB 조회 전, 로그아웃 제한은 토큰 폐기 전에 같은 IP별 한도로 적용한다. `LLM_PROVIDER=fake`는 `ENVIRONMENT=test`에서만 허용하고 그 외 환경은 시작을 거부한다. 챗봇 LLM 설정은 위 `DIT_API_LLM_*` 값만 생성자 인자로 받으며, 접두사 없는 `DATABASE_URL`·`DB_AUTO_INIT`·`ADMIN_TOKEN` 같은 프로세스 환경 변수나 `.env`를 읽지 않는다. LLM 실패 로그에는 예외 종류만 남긴다. 과거 standalone 학번 토큰은 공통 UUID 인증으로 승인된 것이 아니며, 실서버에서 임시 fallback으로 사용하지 않는다. 상세 재현과 미검증 범위는 [PR39 후속 보안 검토](../../docs/dev-prep/PR39_AUTH_DB_SAFETY_REVIEW.md)와 [PR28 독립 보안 리뷰 수정 기록](../../docs/dev-prep/PR28_CLAUDE_SECURITY_REVIEW.md)을 본다.

**현재 상태:** 학번 로그인과 토큰 개인 질문은 `test` 환경의 격리 메모리 회귀 외 모든 환경에서 의도된 503(fail-closed)이며 동작하는 서비스가 아니다. 이는 DEC-020이 승인한 운영 경로(학번 로그인, migration 계정의 `app.seed_demo` 명시 실행)를 공통 bridge 전까지 임시로 좁힌 것이며, 사람의 명시적 확인이 대기 중이다. 결정 자체를 바꾸거나 승인된 것으로 간주하지 않는다.

테스트는 가짜 LLM과 메모리 SQLite로 실행하며 외부 LLM·MariaDB를 호출하지 않는다(`tests/test_ai_ask.py`). 요청 제한은 프로세스 메모리 기준이라 워커 1개를 전제하며, `request.client.host`만 사용하고 `X-Forwarded-For`를 신뢰하지 않는다. 신뢰 프록시 IP 추출·만료 저장소·분산 제한은 배포 전 게이트다.

## 실행과 검증

Python 3.13과 uv 0.13.6을 사용한다. `uv.lock`을 함께 커밋한다. 의존성 변경 때만 `uv lock`하고, 평소에는 잠금 파일을 검증한다. [uv 공식 안내](https://docs.astral.sh/uv/concepts/projects/sync/)의 `--locked` 동작을 따른다.

```powershell
cd services/api
uv sync --locked
$env:DIT_API_ENVIRONMENT = 'development'
$env:DIT_API_DOCS_ENABLED = 'true'
$env:DIT_API_CORS_ORIGINS = '["http://localhost:5173"]'
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Linux/macOS에서는 동일한 `DIT_API_*` 환경 변수를 `export`로 설정한다. 앱은 `.env`를 자동 읽지 않는다. `.env.example`은 키 설명이며 비밀값이 없다. 환경 종류는 필수이고 누락/잘못된 값이면 시작을 거부한다. CORS는 기본 비허용, 명시한 origin만 허용하며 쿠키 자격 증명은 활성화하지 않는다. 인증 방식 선택 시 CORS·CSRF·세션 정책을 별도 리뷰한다.

```text
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked python -c "from app.main import app; assert app.openapi()['paths']"
```

마지막 명령에도 `DIT_API_ENVIRONMENT=test` 등이 필요하다. OpenAPI HTTP 문서는 기본 비활성이며 `DIT_API_DOCS_ENABLED=true`이면 `/docs`, `/openapi.json`에서 확인한다. 모든 실제 API 응답에는 서버 생성 `X-Request-ID`가 있다. CORS preflight는 CORS 계층에서 처리한다.

## 계층과 오류·로그

라우터 → 상태 확인 서비스 → 선택적 readiness probe 인터페이스로 분리한다. 지금은 DB 어댑터가 없으므로 probe를 연결하지 않는다. 도메인 저장소 인터페이스는 실제 소비 태스크에서 추가한다. FastAPI/Pydantic 공통 모델과 JSON 오류는 `/api/v1` 계약을 따른다. 입력 검증은 400, 존재하지 않는 경로는 404, 예기치 않은 실패는 500이다. 오류 응답은 `code/message/field_errors/retryable/request_id`를 반환하며 입력 원문·내부 예외를 넣지 않는다.

앱 로그는 요청 ID·정해진 이벤트·메서드·상태 코드만 남긴다. 요청 URL/쿼리/본문/헤더와 예외 문자열은 기록하지 않는다. Uvicorn 기본 access log는 URL을 남기므로 실행 명령에 `--no-access-log`를 사용한다. 배포 프록시·서버 로그도 별도 검토가 필요하다.

## 다음 게이트

MariaDB 제품은 사용자 결정으로 확정되었다. OPEN-002(DB 운영 접속·인증·호스팅·비용), OPEN-003(가상 권한 시드 책임자) 결정 후 인증 dependency·DB 어댑터·가상 시드를 별도 PR로 구현한다. FastAPI 선택과 코드 기반 검증은 실제 학교 연동·운영 준비 완료를 뜻하지 않는다.

GitHub의 `Python API 검증`은 잠금 설치·Ruff·pytest·앱 import/OpenAPI·에이전트 설정을 검사한다. 기존 `MVP 검증`도 같은 PR에서 타입과 빌드를 실행한다. 배포·비밀값·인증/DB 접근을 요구하지 않는다.

## 실제 API와 프런트 타입 동기화

`uv run --locked python -m app.export_openapi`로 실제 라우트에서 `openapi.json`을 생성하고 `--check`로 커밋된 스냅샷과 비교한다. 기존 CI의 `mvp/` 타입 생성·검사는 사전 프로토타입의 역사적 회귀만 유지한다. 생성 타입 갱신은 기존 소스를 새 제출물에 재사용하는 행위가 아니다. 신규 앱은 별도 타입 생성기와 공개 조회의 실제 API 연결 검증을 갖추었다. 타입 생성은 [openapi-typescript의 공식 Node API](https://openapi-ts.dev/node)를 사용한다.

현재 계약에는 health 두 경로, 공개 시설 검색, 공개 대학·학과 안내 조회 두 경로와 공통 응답/오류가 있다. 인증·학생 CRUD가 아직 없으므로 생성 타입은 그것들의 동작을 주장하지 않는다. MariaDB·공통 세션 통합은 별도로 검증한다.

## MariaDB 비연결 설정 기반 — TASK-DB-CONFIG

MariaDB 11.4, 플랫폼 `ditnow`, 런타임 `ditnow_app`(DML 전용), 별도 `ditnow_migrator`라는 사용자 결정을 따른다. `.env.example`의 `DIT_API_DB_*`는 비밀값 없는 설명이며, 실제 사설 주소·비밀번호는 저장하지 않는다. 설정이 전혀 없으면 공개 API는 계속 실행할 수 있다. HOST/USER/PASSWORD 일부만 있거나 다른 DB·관리자 계정이면 설정 검증이 실패한다. 포트 기본값은 3307이다. 이 검증은 실제 GRANT 검사를 대신하지 않는다.

`app/core/db_connection.py`는 SQLAlchemy async + aiomysql 엔진을 **생성만** 하며 앱 factory·라우터·readiness에 연결하지 않는다. 마이그레이터 자격 증명, DDL, 자동 스키마 생성, 인증 공급자 구현은 포함하지 않는다. TASK-N은 승인 대기 PR #19/26을 격리 조합하여 SQLAlchemy P0 저장소와 async `run_sync` 실행 경계를 작성한다. 라우터에 연결하지 않으며 실제 DB 적용 전에 독립 리뷰·사람 승인을 받는다. 한 서비스 트랜잭션은 하나의 async session에서 실행한다.

이 엄격한 factory는 `DIT_API_DB_*`만 사용한다. PR39의 legacy `DIT_API_DATABASE_URL`/학번 원장 경로와 별개이며 해당 경로를 승인하거나 TLS factory로 자동 대체하지 않는다. legacy 원격 원장·시드 안전 차단 보완은 승인 대기 PR28에서 검토하므로, 그 경로를 공통 인증·실제 운영 준비로 사용하지 않는다.

TLS 인증서와 호스트명 검증을 필수로 한다. 별도 CA가 없으면 시스템 신뢰 저장소를 사용하며 검증을 완화하지 않는다. aiomysql 0.3.2의 TLS 미지원 서버 fallback을 막기 위해 인증 직전의 private hook에서 TLS capability와 검증 설정을 검사한다. 따라서 드라이버 버전을 고정했으며 버전 변경 시 해당 hook 재검토와 핸드셰이크 테스트가 필요하다. 테스트는 가짜 연결에서 인증 위임 전 차단을 확인하며 실제 서버 TLS·인증 성공을 증명하지 않는다. LOCAL INFILE, autocommit, SQL echo는 비활성이다. 엔진 URL에는 자격 증명을 넣지 않는다.

```text
uv run --locked python -m app.core.db_connection
uv run --locked pytest tests/test_db_configuration.py
```

첫 명령은 **오프라인 설정 진단**만 출력한다. 호스트·계정·비밀번호·DSN·내부 예외는 출력하지 않으며 연결/GRANT는 `NOT_RUN`이다. `DIT_API_ENVIRONMENT`는 기존처럼 필수다. 스키마 버전 원장의 테이블/권한/기대 버전이 아직 승인되지 않아 `BLOCKED_LEDGER_CONTRACT`로 표시한다. 임의의 원장 테이블을 조회하거나 현재 스키마를 최신으로 간주하지 않는다. 접속 승인 후 실제 MariaDB 11.4/utf8mb4/utf8mb4_unicode_ci·TLS·DML 최소 GRANT·스키마 버전 검사를 추가해야 하며, 그 전에는 운영 준비 완료로 표시할 수 없다.

확인일 2026-10-30: [SQLAlchemy MariaDB·aiomysql 공식 문서](https://docs.sqlalchemy.org/en/20/dialects/mysql.html#module-sqlalchemy.dialects.mysql.aiomysql)는 async dialect를 제공하고, [aiomysql 연결 문서](https://aiomysql.readthedocs.io/en/stable/connection.html)는 SSLContext·connect_timeout·LOCAL INFILE 설정을 설명한다. 이는 실제 팀 VM과의 호환성 검증을 대체하지 않는다. 사설망·계정·GRANT 및 루프별 엄격 TLS 실험은 별도 [운영 검사](../../docs/dev-prep/07_DB_CONNECTIVITY_AND_ROLES.md) 기록을 따른다. 과거 BLOCKED_TLS의 원인을 모든 경우 인증서 실패로 간주하지 않는다. 원격 DDL·seed·CRUD 쓰기를 이 호환 보완에서 수행하지 않았으며 사람 승인 전 자동 병합하지 않는다. 관련 요구사항: NFR-SEC-004/005, NFR-PRIV-003, NFR-OPS-001/002; 로컬 검증 ID: TC-DB-CONFIG.

## Windows 비동기 DB 호환 실행 — 승인 대기 보완

root의 2026-10-30 별도 진단 보고에서 CA·호스트 검증을 유지한 TLS-only handshake는 성공했고 인증 패킷을 보내지 않았다. 기본 Proactor 실행 실패는 `OperationalError(2003) → OSError(22) → SSLWantReadError`로 분류되었으며 인증서 검증 오류와 구분한다. 같은 엄격 factory를 Selector 루프로 실행한 별도 실험에서는 DML 계정 인증·SELECT1이 성공했지만 안정 운영·동시성·업무 CRUD의 VERIFIED 판정은 아니다. 이 수정 작업자는 원격 접속·실제 비밀값 조회를 수행하지 않았다. 새 커밋의 실제 서버 재검증은 별도 승인된 운영자 작업이다.

`app.core.event_loop.new_event_loop`는 Windows에서 Selector를, Unix에서 asyncio의 설정된 기본 루프를 생성한다. import 시 루프를 만들거나 전역 `set_event_loop_policy`를 변경하지 않는다. 설치된 Uvicorn 0.54.0의 custom loop 경로와 실제 `Config.get_loop_factory()` 반환 callable을 오프라인 테스트했다. [Uvicorn custom loop 안내](https://uvicorn.dev/concepts/event-loop/#custom-event-loop), [Python 3.13 Windows 제한](https://docs.python.org/3.13/library/asyncio-platforms.html#windows)을 확인했다(2026-10-30).

```powershell
# 기존 DIT_API_* 설정과 엄격한 CA/호스트 검증을 그대로 유지한다.
uv run --locked uvicorn app.main:app --loop app.core.event_loop:new_event_loop --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

이는 개발/호환성용 단일 프로세스 실행 경로다. Windows Selector는 512 소켓 제한 및 subprocess/pipe 미지원 제약이 있어 대규모 동시성·다중 worker·reload·하위 프로세스 작업의 운영 준비를 주장하지 않는다. Linux 운영은 기존 기본 루프 경로를 유지한다. 실행 명령만으로 DB 어댑터·로그인·보호 라우트를 활성화하지 않는다.

명시적 opt-in인 `python -m app.db.live_check`도 같은 loop factory를 사용하며 승인된 운영자만 실행한다. opt-in이 없으면 설정 조회·루프 생성·네트워크 없이 NOT_RUN이다. 조회는 버전/세션 정렬/DB명/스키마 이름 검사이며 원격 DDL·시드·업무 데이터 쓰기를 하지 않는다. 연결 성공과 16개 제안 테이블 준비·제약·권한·업무 승인 상태는 서로 별개다.

SQLAlchemy MySQL dialect의 내부 `SET NAMES utf8mb4`가 드라이버 `init_command`의 collation을 덮어쓰는 것을 설치 소스로 확인했다. `db_connection.py`는 engine 생성 뒤 `connect` 리스너를 **append**하여 최종 `SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci`를 실행한다(`insert=True` 금지). 사용자 입력을 SQL에 넣지 않으며 테이블/지속 데이터 변경은 없다. 설정 실패 시 커서를 정리하고 비밀값 없는 오류로 연결 준비를 거부한다. [SQLAlchemy async 이벤트](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-events-with-the-asyncio-extension)·[연결 이벤트 순서](https://docs.sqlalchemy.org/en/20/dialects/mysql.html#changing-the-sql-mode)를 따른다. 실제 dialect listener 뒤에 정적 COLLATE 문이 실행되는 회귀와 실패 경로를 오프라인 검사한다. 기존 TLS capability·CERT_REQUIRED·check_hostname·LOCAL INFILE 금지·DML 계정 분리·비밀 로그 보호를 완화하지 않는다. 전체 연결/업무 SQL의 시간 제한과 다중 프로세스 안정성은 별도 검증 범위다.

## 바이트 파라미터 호환 검사

잠금 조합 aiomysql 0.3.2·PyMySQL 1.2.3은 바이트 바인딩에서 import 전용 내부 항목을 함수로 호출해 신원 해시 충돌 조회가 실패했다. 엄격 연결 클래스의 bytes/bytearray만 PyMySQL의 이진 hex 리터럴 표현으로 보완한다. TLS·현재 권한·원장 타입은 그대로 검증하며 드라이버 글로벌 패치나 보안 버전 하향은 하지 않는다. API의 PyMySQL 범위는 `>=1.2.3,<1.3`이다.

`tests/test_db_binary_parameters.py`는 실제 잠금 DBAPI의 바이트 전 범위·인용 경계·SQL 모드와 기존 타입을 네트워크 없이 검사한다. 실제 원격 읽기 전용 왕복과 25개 테이블 준비 결과, 계정 생성 승인 전의 미실행 범위는 [재검증 기록](../../docs/dev-prep/TASK_MARIADB_LIVE_REVALIDATION.md)을 따른다. 기본 오프라인 테스트를 실제 계정·업무 CRUD 검증으로 표시하지 않는다.

## 공개 통합 검색

GET `/api/v1/discovery`는 기존 공개 안내·시설 검색 서비스를 읽기 전용으로 조합한다. 정규화 검색·종류 필터·bounded 집계/페이지와 근거를 제공하며 개인정보·DB·LLM을 조회하지 않는다. 신규 앱 `/app/search`와 안내/시설 상세 링크에 연결했다. 전체 서비스 검색 완료를 뜻하지 않으며 [TASK-P](../../docs/dev-prep/TASK_PUBLIC_DISCOVERY_IMPLEMENTATION.md)를 따른다.

## 공개 대학·학과 안내
GET `/api/v1/public-campus`와 `/{record_id}`는 근거 7건을 자체 요약한 버전 스냅샷의 목록·정규화 검색·주제/출처 필터·상세를 제공한다. 새 앱 `/app/information`에 연결했다. 공식 게시물 동일성·실시간 최신성·학과 운영 업무 전체를 주장하지 않는다. 상세 범위와 출처는 [TASK-I](../../docs/dev-prep/TASK_PUBLIC_CAMPUS_IMPLEMENTATION.md)를 본다. 쓰기·개인 신원·실DB 접근은 없다.

MariaDB 실제 두 계정 읽기/권한 검증과 비동기 TLS 연결 차단은 [운영 검사](../../docs/dev-prep/07_DB_CONNECTIVITY_AND_ROLES.md)를 따른다. CA·SAN 준비 전 인증서 검증을 해제하지 않는다. `infra/mariadb` 서버 운영 정의를 이 개발 PC에서 실행하지 않는다.
