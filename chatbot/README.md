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

통합 라우터의 공용 등록과 `services/api`의 로컬 의존성 잠금은 공통 파일 소유자가 별도로 반영한다. 등록 전에는 통합 서비스에 배포된 것으로 표시하지 않는다.

## 설치와 검증

Python 3.11 이상에서 사용한다. 통합 API의 Python 3.13과 공존하며, 내부 상대 import는 기존 `uvicorn app.main:app` 실행도 보존한다.

```powershell
# chatbot/에서 기존 독립 시연 회귀 검사. 외부 LLM은 호출하지 않는다.
uv sync --locked --all-extras
uv run --locked --all-extras ruff check .
uv run --locked --all-extras pytest -q

# services/api/의 공통 pyproject/uv.lock에 로컬 의존성이 반영된 이후
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
