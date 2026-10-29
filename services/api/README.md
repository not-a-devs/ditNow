# DIT NOW FastAPI 기반

TASK-B · NFR-SEC-004/005, NFR-PRIV-003, NFR-REL-004, NFR-OPS-001/002의 기반 코드다. 공개 `/health`, `/api/v1/health`는 프로세스 생존만 확인한다. 인증·DB·학생 CRUD는 아직 구현되지 않았으며 DB 준비 성공으로 표시하지 않는다. 최종 프런트는 별도 신규 앱이며 `mvp/`는 사전 프로토타입으로 보존하고 최종 서비스·시연·제출에서 제외한다. 해당 코드를 새 앱에 복사하지 않는다.

TASK-F는 [기존 챗봇](../../chatbot/README.md)의 검색기를 통합 API의 `GET /api/v1/ai/campus/search`에 연결한다. 시설 스냅샷 검색만 제공하며 별도 시연 로그인·관리자 API·학생 DB·LLM을 실행하지 않는다. 검색 결과의 공식 출처·최신성은 UNKNOWN이며 개인정보 질문과 전체 AI 브리핑의 완료를 뜻하지 않는다.

## 학번 로그인과 AI 답변 (DEC-020)

챗봇의 의도 분류·후속 질문·개인 질문 계산·LLM 답변을 패키지 함수 그대로 호출한다(복제 없음). 학생·학적은 가상(DEMO) 데이터다.

| 경로 | 설명 |
| --- | --- |
| `POST /api/v1/auth/login` | `{student_id, password}` → Bearer 토큰 (12시간). 시연 계정 `20231001` / `3000001` |
| `POST /api/v1/auth/logout` | 토큰 폐기 |
| `POST /api/v1/ai/ask` | `{question, history?}` + 선택 `Authorization: Bearer`. 교내 질문은 비로그인 허용, 개인 질문은 로그인 필요(`need_login`) |

설정(`DIT_API_` 환경 변수): `DATABASE_URL`(학적 DB, 없으면 로그인·개인 질문 503), `LLM_PROVIDER`·`LLM_MODEL`·`LLM_API_KEY`·`LLM_BASE_URL`(없으면 `/ai/ask` 503, 공개 검색은 동작), `CURRENT_SEMESTER`, `ASK_RATE_LIMIT_PER_MIN`(IP당 분당, 기본 20).

서버 시작 시 테이블을 만들지 않는다. 처음 한 번 migration 계정으로 테이블 생성·가상 데이터 시드를 실행하고, 서버는 DML 계정(`ditnow_app`)으로 띄운다.

```sh
export DIT_API_ENVIRONMENT=development
export DIT_API_DATABASE_URL='mysql+aiomysql://ditnow_migrator:<pw>@<tailscale-ip>:3307/ditnow?charset=utf8mb4'
uv run --locked python -m app.seed_demo   # 학생이 이미 있으면 건너뜀
```

테스트는 가짜 LLM과 메모리 SQLite로 실행하며 외부 LLM·MariaDB를 호출하지 않는다(`tests/test_ai_ask.py`). 요청 제한은 프로세스 메모리 기준이라 워커 1개를 전제한다.

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

## 공개 통합 검색

GET `/api/v1/discovery`는 기존 공개 안내·시설 검색 서비스를 읽기 전용으로 조합한다. 정규화 검색·종류 필터·bounded 집계/페이지와 근거를 제공하며 개인정보·DB·LLM을 조회하지 않는다. 신규 앱 `/app/search`와 안내/시설 상세 링크에 연결했다. 전체 서비스 검색 완료를 뜻하지 않으며 [TASK-P](../../docs/dev-prep/TASK_PUBLIC_DISCOVERY_IMPLEMENTATION.md)를 따른다.

## 공개 대학·학과 안내
GET `/api/v1/public-campus`와 `/{record_id}`는 근거 7건을 자체 요약한 버전 스냅샷의 목록·정규화 검색·주제/출처 필터·상세를 제공한다. 새 앱 `/app/information`에 연결했다. 공식 게시물 동일성·실시간 최신성·학과 운영 업무 전체를 주장하지 않는다. 상세 범위와 출처는 [TASK-I](../../docs/dev-prep/TASK_PUBLIC_CAMPUS_IMPLEMENTATION.md)를 본다. 쓰기·개인 신원·실DB 접근은 없다.

MariaDB 실제 두 계정 읽기/권한 검증과 비동기 TLS 연결 차단은 [운영 검사](../../docs/dev-prep/07_DB_CONNECTIVITY_AND_ROLES.md)를 따른다. CA·SAN 준비 전 인증서 검증을 해제하지 않는다. `infra/mariadb` 서버 운영 정의를 이 개발 PC에서 실행하지 않는다.
