# PR28 독립 보안 리뷰 결과와 수정 기록 (TASK-SEC28-FIX)

> 상태: 2026-10-30. 리뷰는 Claude Code 독립 읽기 전용 세션이 수행했다(기준 HEAD `299ec17`). 수정은 별도 세션이 최신 main 병합 후 PR28 브랜치에서 진행했다.
> 이 문서와 AI 리뷰는 사람의 승인이 아니다. 인증·DB·보안 경계 변경이므로 자동 병합하지 않으며, 사람 승인이 필요하다. VERIFIED·실DB 완료를 주장하지 않는다.

## 1. 판정 요약
| ID | 심각도 | 로컬 재현 | 조치 |
| --- | --- | --- | --- |
| F-01 | 중(거버넌스) | 해당 없음(결정 해석) | 문서로 명시. **사람 확인 대기** |
| F-02 | 중 | **재현됨**: `root_path=/backend`에서 private 응답에 `Cache-Control` 없음 | 수정 |
| F-03 | 하~중 | **재현됨**: 접두사 없는 `DB_AUTO_INIT=true`가 있으면 `build_assistant`가 ValidationError | 수정 |
| F-04 | 중 | **재현됨**: `Settings(environment=production, llm_provider=fake)` 생성 성공 | 수정 |
| F-05 | 하~중 | 코드 확인(배포 조건 의존) | 배포 게이트 유지, 문서화 |
| F-06 | 하(비활성) | **재현됨**: 메모리 test 환경에서 logout이 제한 없이 폐기 호출 | 수정 |
| F-07 | 하(비활성) | 기존 PR39 기록 | 503 유지, BLOCKED |
| F-08 | 하 | 코드 확인 | 문서화, 자동 DDL 추가 안 함 |
| F-09 | 하(비활성) | 코드 확인 | 비활성 게이트로 유지 |
| F-10 | 정보 | 확인 | 수정 |
| F-11 | 정보 | 코드 확인 | `rag.py` 수정. 동일 패턴 2건은 잔여 |

재현은 `services/api/tests/test_security_boundaries.py`를 수정 전 코드에 먼저 실행해 확인했다(39개 중 24개 실패: F-02 18, F-03 2, F-04 2, F-06 2). 가짜 LLM과 프로세스 메모리만 사용했다.

## 2. 수정 내용
- **F-02** `services/api/app/core/logging.py`: exact `scope["path"]` 비교를 Starlette `get_route_path(scope)` 기준 route-relative 판정으로 바꿨다. `/api/v1/auth`와 `/api/v1/ai/ask` 경로 트리(정확 일치 또는 `/` 하위)를 private로 본다. 그래서 `root_path` 접두사, 하위 404, 후행 슬래시 리디렉션도 `private, no-store`다. `/health`, `/api/v1/ai/campus/search`, `/api/v1/ai/asking`·`/api/v1/authx` 같은 유사 경로는 바뀌지 않는다. 서버 `root_path` 설정 없이 클라이언트가 붙인 접두사는 알 수 없는 경로(404)로 처리한다.
- **F-03** `services/api/app/integrations/chatbot/assistant.py`: `IntegratedLLMSettings`(챗봇 `Settings` 하위 클래스)가 `settings_customise_sources`로 입력 소스를 생성자 인자만으로 한정한다. 프로세스 환경 변수, `.env`, secret 파일을 읽지 않는다. `model_construct`를 쓰지 않아 기존 필드 검증기(`db_auto_init` 거부 등)는 그대로 실행된다. `chatbot_llm_settings()`가 `DIT_API_LLM_*` 값만 전달한다.
- **F-04** `services/api/app/core/config.py`: `llm_provider=fake`는 `environment=test`에서만 허용한다. 개발·운영에서는 설정 단계에서 시작을 거부한다. 기존 dev/prod 503 회귀 테스트는 LLM 없이도 토큰 경로가 LLM 호출 전에 503이 되므로 fake 지정을 제거했다.
- **F-06** `services/api/app/api/v1/auth.py`: logout은 토큰 폐기 전에 기존과 같은 IP별 버킷·한도(`ASK_RATE_LIMIT_PER_MIN`)를 소비한다. 한도 값과 login/ask 공유 구조는 바꾸지 않았다. 실서버에서는 여전히 Session 의존성이 503을 반환한다.
- **F-10** assistant 모듈 docstring을 현재 동작에 맞췄다(원격 테이블 생성·시드 안내 제거).
- **F-11** `chatbot/app/rag.py`: LLM 실패 로그에 예외 문자열 대신 예외 종류만 남긴다. 회귀 테스트는 `chatbot/tests/test_rag.py::test_llm_failure_logs_error_type_only`다.

## 3. 유지되는 게이트 (수정하지 않음)
- **F-01 DEC-020 임시 축소:** DEC-020(확정)은 학번+초기 비밀번호 로그인을 승인하고, `app.seed_demo`를 migration 계정으로 명시 실행하도록 정했다. identity 연결은 PR #19 이후 후속으로 둔다. 현재 코드는 공통 UUID·현재 학적 bridge 전까지 다음만 허용한다.
  - 로그인·로그아웃·토큰 개인 질문: `DIT_API_ENVIRONMENT=test`이면서 `DIT_API_DATABASE_URL`이 정확히 `sqlite+aiosqlite:///:memory:`인 격리 프로세스에서만 동작한다. 그 외 모든 환경·URL에서는 503이다.
  - `app.seed_demo`: 정확한 canonical 메모리 URL만 허용하고 다른 대상은 엔진 생성 전에 거부한다. 메모리 DB는 프로세스 종료와 함께 사라지므로 실서버 시드 효과가 없다.
  - DEC-020의 기록된 방향(학번 로그인, 명시적 시드, 시작 시 DDL 없음)은 그대로 보존한다. 이 축소는 승인된 결정 변경이 아니며 AI가 승인했다고 간주하지 않는다. **Product Owner의 명시적 확인 또는 후속 DEC가 병합 전 필요하다.**
- **F-05 요청 제한:** `request.client.host` 기준, 프로세스 메모리, 단일 워커 전제다. 임의 `X-Forwarded-For`를 신뢰하지 않으며, 신뢰 프록시 설정·만료 저장소·분산 제한기 공급자는 추가하지 않았다. 배포 전 게이트다.
- **F-07 legacy 토큰:** UUID·현재 소속 재검증·비밀번호 변경 시 폐기 정책이 없다. bridge 승인 전에는 503을 유지하며 BLOCKED 상태다.
- **F-08 standalone 챗봇:** `uvicorn app.main:app`은 승인된 DB factory가 없어 어떤 구성에서도 실행되지 않는다(의도된 fail-closed). 실행 가능하다고 해석하지 않으며, 자동 DDL로 우회하지 않는다.
- **F-09 엔진 폐기:** 승인 factory가 거부될 때 엔진을 dispose하려면 비동기 설계가 필요하다. 동기 경로에서 비동기 dispose를 억지로 호출하지 않고, 승인 factory 도입 때 함께 설계하는 비활성 게이트로 남긴다.
- 개인 DB 원격 활성화, 엄격 TLS 완화, UUID bridge 게이트 우회는 하지 않았다. 실제 원격 TLS 검증 증거는 root 소유이며 이 작업의 증거가 아니다.

## 4. 잔여 위험
- F-11과 같은 원문 예외 로그가 `chatbot/app/intents.py`(의도 분류 실패)와 `chatbot/app/conversation.py`(후속 질문 재작성 실패)에도 있다. 둘 다 통합 `/ai/ask` 경로에서 호출된다. 이번 작업의 소유 경로가 아니라서 수정하지 않았으므로 후속 담당자가 같은 방식으로 수정해야 한다.
- no-store 판정은 경로 트리 allowlist다. `/api/v1` 아래에 새 private 경로를 추가하면 private 접두사 등록이나 경로별 헤더가 함께 필요하다.

## 5. 실행한 검증 (2026-10-30, 로컬)
- `services/api`: 대상 테스트(`test_security_boundaries.py`, `test_assistant_safety.py`, `test_ai_ask.py`, `test_foundation.py`) 93 PASS. 전체 pytest 893 PASS. Ruff check·format PASS. `DIT_API_ENVIRONMENT=test python -m app.export_openapi --check` 일치.
- `chatbot`: 전체 pytest 152 PASS. Ruff check·format PASS.
- NOT_RUN: 실제 MariaDB·원격 DB·TLS·GRANT, 실제 LLM, 프록시/CDN 캐시 동작, 다중 워커 제한, 신규 웹 검사(변경 없음). SQLite·가짜 LLM 결과는 MariaDB 증거가 아니다.
