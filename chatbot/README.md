# DIT NOW 챗봇 구성요소

챗봇은 DIT NOW 통합 플랫폼의 기능이다. 별도 사용자 원장이나 최종 제품으로 운영하지 않는다.
`app/main.py`의 기존 독립 시연 실행 경로는 회귀 확인을 위해 보존하며, 그 로그인·세션·자동 DB 시드·관리자 API를 통합 앱에 연결하지 않는다.

## 통합 1단계 — 공개 시설 검색

- 패키지 이름: `ditnow-chatbot`, import 경로: `chatbot.app`.
- 통합 어댑터: `services/api/app/integrations/chatbot/campus.py`.
- 라우터: `services/api/app/api/v1/ai.py`의 `router`.
- 계약: `GET /api/v1/ai/campus/search?q=컴소과&limit=5`.
- 기존 `load_data`와 `KeywordRetriever`를 그대로 호출한다. 검색 로직을 복제하지 않는다.
- `data/buildings.json`, `data/facilities.json`만 읽는다. 학생 목업, 학적 원장, 별도 로그인, DB, LLM 클라이언트는 로드하지 않는다.
- 응답은 공통 `SuccessResponse` 안의 검색 결과다. `mode=retrieval_only`, `generated=false`, `personal_data_access=false`를 명시한다.
- 원본 시설 스냅샷의 항목별 공식 출처·최신성은 확인되지 않았으므로 `verification=UNKNOWN`으로 표시한다. 실시간 학교 데이터나 공식적으로 검증된 원장이라고 표시하지 않는다.
- 질문·위치·대화 기록을 저장하거나 검색 캐시에 넣지 않는다. 캐시는 읽기 전용 시설 검색 인덱스 하나만 보관한다.

통합 라우터의 공용 등록과 `services/api`의 로컬 의존성 잠금을 반영했다. 통합 앱의 실제 경로로 검색을 테스트하지만 운영 배포·신규 프런트 연결은 별도 검증 대상이다.

## 설치와 검증

Python 3.11 이상에서 사용한다. 통합 API의 Python 3.13과 공존하며, 내부 상대 import는 기존 `uvicorn app.main:app` 실행도 보존한다.

```powershell
# chatbot/에서 기존 독립 시연 회귀 검사. 외부 LLM은 호출하지 않는다.
uv sync --locked --all-extras
uv run --locked --all-extras ruff check .
uv run --locked --all-extras pytest -q

# services/api/에서 통합 API 검사
uv sync --locked
uv run --locked pytest -q
```

패키지 기본 의존성은 Pydantic과 RapidFuzz뿐이다. `standalone` extra의 DB·외부 LLM SDK는 기존 시연 회귀용이며, 통합 공개 검색의 실행 조건이 아니다. 통합 환경에 외부 API 키나 DB 접속 정보가 필요하지 않다.

## 요구사항과 상태

| 범위 | 관련 ID | 실제 상태 |
| --- | --- | --- |
| 시설 검색·위치 안내 | FR-CAMP-001, TC-V1-CAMP-001 | 부분 구현: 시설 검색 어댑터와 API 테스트. 예약·실제 지도·DB 연동은 미구현 |
| 개인정보 기반 브리핑 | FR-AI-001, TC-V1-AI-001 | BLOCKED: 공통 로그인·사용자·학적 원장과 승인된 데이터 접근 계약 필요 |
| 공고 요약·추천 | FR-AI-002/003 | 미구현: 외부 모델 공급자·비용·사용량 제한 승인 필요 |
| 개인정보 최소화·공통 오류 | NFR-PRIV-002/003, NFR-AI-001/002/003/004 | 검색 데이터 경계·응답 모델·입력 제한 테스트. 실제 모델·원장·운영 남용 제한 검증은 미수행 |

향후 개인 질문은 `services/api`에서 검증한 공통 사용자 신원과 권한을 통해 허용된 학적 데이터만 조회한다. `chatbot`의 기존 시연 학생 테이블·토큰을 통합 인증의 원장으로 채택하지 않는다. MariaDB 제품 선택은 확정되었지만 클라우드 접속·비용·운영 권한 구성은 이 작업에서 수행하지 않는다.

## DB 런타임 안전 전환 제안 (TASK-F-DB-SAFETY · 사람 승인 전 병합 금지)

- `DB_AUTO_INIT=false`가 기본이다. 기존 환경의 `true`는 설정 오류로 거부하며 앱 시작에서 `create_all`, `drop_all`, 학생·계정 시드 작업을 제거했다.
- 보존된 독립 시연 서버는 기존 필수 테이블의 존재를 읽기 전용으로 확인한다. 테이블 부재·DB 접근 실패 시 안전한 메시지로 시작을 거부하고 임의 복구·스키마 생성은 하지 않는다. 필수 테이블 존재 검사는 컬럼·제약·스키마 버전·실제 GRANT 검증을 뜻하지 않는다.
- `init_db`는 폐기 가능한 SQLite 메모리 테스트 전용이다. 파일 SQLite나 MariaDB에서 초기화/reset을 시도하면 연결 전에 거부한다. `seed_db.py --reset`은 지원하지 않으며 명시한 메모리 테스트만 허용한다.
- 운영 스키마 변경·시드는 공통 MariaDB 마이그레이션 책임자와 별도 계정의 승인 작업이다. 기존 `students`/`auth_sessions`를 별도 원격 스키마에 새로 만들어 플랫폼 신원 원장과 이중으로 운영하는 마이그레이션은 제공하지 않는다. 통합 신원 매핑과 허용 학적 조회 계약 확정 전 이 작업은 BLOCKED다.
- 앱 DML 계정과 마이그레이션 계정의 분리는 운영 요구사항이며, 실제 GRANT를 확인했다는 뜻이 아니다. DB 접속 비밀번호·클라우드 접속이 준비되지 않아 실제 MariaDB 접근·DDL·데이터 변경·마이그레이션은 NOT_RUN이다. 기존 인스턴스 외 새 컨테이너를 만들지 않았다.
- DSN·LLM 키·관리자 토큰은 SecretStr로 다루며 설정 repr/JSON 출력에서 숨긴다. 메모리 테스트 엔진에도 hide_parameters를 적용한다. 정확한 `sqlite+aiosqlite:///:memory:` 이외의 연결은 승인된 공통 엔진 factory가 주입되기 전 생성 단계에서 거부한다. TLS·서버 인증서·연결/읽기/쓰기 timeout은 공통 DB 소유자의 정책을 주입해야 하며 별도 중복 드라이버 hook은 만들지 않는다. 현재 그 원격 factory는 연결하지 않았다.
- DB 오류의 SQL·바인딩된 질문·연결 정보를 질문 감사 실패 로그에 기록하지 않는다. 기존 독립 로그인은 여전히 통합 앱에 mount하지 않는다.

`.env.example`의 DB 주소는 호스트/자격 증명 자리표시자와 포트 3307을 제공한다. 실제 비밀값은 저장소 밖에서 구성한다. 원격 운영 DB에 이 독립 시연의 테스트 시드를 실행하지 않는다.

2026-10-30 코드 제안 검증: 기존 챗봇+안전 회귀 `pytest` 146개 PASS, Ruff 검사·37개 포맷 PASS, 통합 API 37개 PASS와 OpenAPI 스냅샷 일치. 초기화 검사는 격리 SQLite 메모리/임시 경로만 사용했고 파일 DB/원격 DSN/query가 붙은 메모리 URI의 초기화·reset 거부를 검사했다. 설정 repr/JSON의 비밀값 숨김과 원격 factory 미설정 거부도 검사했다. 실제 MariaDB 연결·GRANT·DDL·시드는 실행하지 않았다.
