# DIT NOW FastAPI 기반

TASK-B · NFR-SEC-004/005, NFR-PRIV-003, NFR-REL-004, NFR-OPS-001/002의 기반 코드다. 공개 `/health`, `/api/v1/health`는 프로세스 생존만 확인한다. 인증·DB·학생 CRUD는 아직 구현되지 않았으며 DB 준비 성공으로 표시하지 않는다. 최종 프런트는 별도 신규 앱이며 `mvp/`는 사전 프로토타입으로 보존하고 최종 서비스·시연·제출에서 제외한다. 해당 코드를 새 앱에 복사하지 않는다.

TASK-F는 [기존 챗봇](../../chatbot/README.md)의 검색기를 통합 API의 `GET /api/v1/ai/campus/search`에 연결한다. 시설 스냅샷 검색만 제공하며 별도 시연 로그인·관리자 API·학생 DB·LLM을 실행하지 않는다. 검색 결과의 공식 출처·최신성은 UNKNOWN이며 개인정보 질문과 전체 AI 브리핑의 완료를 뜻하지 않는다.

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

`uv run --locked python -m app.export_openapi`로 실제 라우트에서 `openapi.json`을 생성하고 `--check`로 커밋된 스냅샷과 비교한다. 기존 CI의 `mvp/` 타입 생성·검사는 사전 프로토타입의 역사적 회귀만 유지한다. 생성 타입 갱신은 기존 소스를 새 제출물에 재사용하는 행위가 아니다. 신규 앱은 별도 타입 생성기와 실제 API 연결 검증을 갖춘 후 사용한다. 타입 생성은 [openapi-typescript의 공식 Node API](https://openapi-ts.dev/node)를 사용한다.

현재 계약에는 health 두 경로, 공개 시설 검색과 공통 응답/오류가 있다. 인증·학생 CRUD가 아직 없으므로 생성 타입은 그것들의 동작을 주장하지 않는다. 신규 프런트 연결과 MariaDB·공통 세션 통합은 별도로 검증한다.

## MariaDB 비연결 설정 기반 — TASK-DB-CONFIG

MariaDB 11.4, 플랫폼 `ditnow`, 런타임 `ditnow_app`(DML 전용), 별도 `ditnow_migrator`라는 사용자 결정을 따른다. `.env.example`의 `DIT_API_DB_*`는 비밀값 없는 설명이며, 실제 사설 주소·비밀번호는 저장하지 않는다. 설정이 전혀 없으면 공개 API는 계속 실행할 수 있다. HOST/USER/PASSWORD 일부만 있거나 다른 DB·관리자 계정이면 설정 검증이 실패한다. 포트 기본값은 3307이다. 이 검증은 실제 GRANT 검사를 대신하지 않는다.

`app/core/db_connection.py`는 SQLAlchemy async + aiomysql 엔진을 **생성만** 하며 앱 factory·라우터·readiness에 연결하지 않는다. 마이그레이터 자격 증명, DDL, 자동 스키마 생성, 인증 공급자 구현은 포함하지 않는다. PR #19의 동기 모델/저장소 초안은 승인 대기이며, 아직 이 async 엔진으로 실행되는 저장소가 아니다. 후속 어댑터는 한 트랜잭션에서 하나의 async session을 사용하도록 별도 검토한다.

TLS 인증서와 호스트명 검증을 필수로 한다. 별도 CA가 없으면 시스템 신뢰 저장소를 사용하며 검증을 완화하지 않는다. aiomysql 0.3.2의 TLS 미지원 서버 fallback을 막기 위해 인증 직전의 private hook에서 TLS capability와 검증 설정을 검사한다. 따라서 드라이버 버전을 고정했으며 버전 변경 시 해당 hook 재검토와 핸드셰이크 테스트가 필요하다. 테스트는 가짜 연결에서 인증 위임 전 차단을 확인하며 실제 서버 TLS·인증 성공을 증명하지 않는다. LOCAL INFILE, autocommit, SQL echo는 비활성이다. 엔진 URL에는 자격 증명을 넣지 않는다.

```text
uv run --locked python -m app.core.db_connection
uv run --locked pytest tests/test_db_configuration.py
```

첫 명령은 **오프라인 설정 진단**만 출력한다. 호스트·계정·비밀번호·DSN·내부 예외는 출력하지 않으며 연결/GRANT는 `NOT_RUN`이다. `DIT_API_ENVIRONMENT`는 기존처럼 필수다. 스키마 버전 원장의 테이블/권한/기대 버전이 아직 승인되지 않아 `BLOCKED_LEDGER_CONTRACT`로 표시한다. 임의의 원장 테이블을 조회하거나 현재 스키마를 최신으로 간주하지 않는다. 접속 승인 후 실제 MariaDB 11.4/utf8mb4/utf8mb4_unicode_ci·TLS·DML 최소 GRANT·스키마 버전 검사를 추가해야 하며, 그 전에는 운영 준비 완료로 표시할 수 없다.

확인일 2026-10-30: [SQLAlchemy MariaDB·aiomysql 공식 문서](https://docs.sqlalchemy.org/en/20/dialects/mysql.html#module-sqlalchemy.dialects.mysql.aiomysql)는 async dialect를 제공하고, [aiomysql 연결 문서](https://aiomysql.readthedocs.io/en/stable/connection.html)는 SSLContext·connect_timeout·LOCAL INFILE 설정을 설명한다. 이는 실제 팀 VM과의 호환성 검증을 대체하지 않는다. 실제 사설망 연결·DB 인증·GRANT·DDL·스키마 상태 검증은 모두 **NOT_RUN**이며 사람 승인 전 자동 병합하지 않는다. 관련 요구사항: NFR-SEC-004/005, NFR-PRIV-003, NFR-OPS-001/002; 로컬 검증 ID: TC-DB-CONFIG.
