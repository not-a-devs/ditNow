# FastAPI 개발 상태와 승인 게이트

> 현재 기준(2026-10-30): MariaDB11.4 팀원 VM·Tailscale 전용/계정 분리는 DEC-019로 확정. [실제 DB 연결 검사](07_DB_CONNECTIVITY_AND_ROLES.md)는 TCP timeout·로컬 Tailscale offline이며 인증/GRANT/migration NOT_RUN이다. 아래 초기 TASK-B/C/D1 기록의 DB 후보·별도 챗봇 표현은 당시 이력이다. PR22 이후 공개 시설 검색은 통합 FastAPI에 연결됐으며 개인 원장·별도 로그인/DB·LLM은 로드하지 않는다. 신규 앱은 apps/web, 사전 mvp는 최종 제출/시연/복사 대상에서 제외한다.

2026-10-30 KST · TASK-B. 관련 기준: NFR-SEC-004/005, NFR-PRIV-003, NFR-REL-004, NFR-OPS-001/002. 이 기반은 API-ID/COM/OPP의 공통 실행 환경이며 FR-AUTH-001 또는 학생 CRUD가 완료됐다는 뜻이 아니다.

| 범위 | 상태 | 증거 |
|---|---|---|
| FastAPI 공개 `/health`, `/api/v1/health` | IMPLEMENTED / TESTED | 실제 Uvicorn HTTP 요청 성공, 프로세스 종료 확인 |
| 공통 Pydantic 성공·오류 모델, 안전한 전역 예외, 요청 ID | IMPLEMENTED / TESTED | pytest의 정상·검증·404/405·도메인 오류·예상외 오류 검사 |
| 환경 설정·기본 거부 CORS·로그 최소화 | IMPLEMENTED / TESTED | 누락/부정 설정, 명시 origin, 비밀값 응답/로그 비노출 검사 |
| Python 의존성 | IMPLEMENTED / TESTED | Python3.13·uv0.13.6, pyproject.toml + uv.lock, `uv sync --locked` |
| Python CI | IMPLEMENTED | TASK-C의 `.github/workflows/python-api-ci.yml`에서 잠금 설치·Ruff·pytest·앱 import/OpenAPI·에이전트 설정 검사. 실제 GitHub 실행 결과는 해당 PR에 기록 |
| 실제 OpenAPI→프런트 타입 생성 | IMPLEMENTED / TESTED | TASK-D1의 public health 스냅샷과 TypeScript 생성·드리프트 검사. 인증/학생 CRUD 경로는 포함하지 않음 |
| 인증/권한/DB/RLS·학생 업무 CRUD | BLOCKED / NOT_RUN | OPEN-002/003 및 도메인 승인 게이트 필요 |

로컬 검증: Ruff 정적 검사·포맷 통과, pytest 22개 통과, 앱 import/OpenAPI 생성 통과, MVP npm ci/typecheck/build 통과, 에이전트 설정·Git diff 검사 통과. TestClient의 httpx 사용 중단 예정 경고 1건은 라이브러리 경고로 남아 있다. 배포·프록시 로그·다중 계정/DB/부하 시험은 NOT_RUN이다.

독립 Codex 코드 리뷰에서 405의 Allow 헤더 누락을 발견했고 안전한 메서드 허용 목록으로 보존한 뒤 회귀 테스트를 통과했다. 사용자 요청으로 실행한 별도 Claude Code의 PR #11 설계 리뷰는 [후속 계약 PR #13](https://github.com/not-a-devs/ditNow/pull/13)에서 수용·보류 여부를 기록한다. AI 리뷰는 사람의 정책·권한 승인이 아니다.

실행법은 [API README](../../services/api/README.md), 현재 프런트 범위는 [MVP README](../../mvp/README.md)를 따른다. 이 문서의 TESTED는 명시된 공개 기반에 한하며 운영 환경 VERIFIED를 뜻하지 않는다.

작업 중 병합된 PR #14의 `chatbot/`은 별도 RAG/개인질문/시연 세션·MariaDB 어댑터 코드로 보존했다. 해당 모듈의 DB·외부 LLM·인증을 이 태스크에서 실행하거나 통합하지 않았다. 두 서버는 서로 다른 `app` 패키지와 설정이므로 디렉터리별 가상환경을 사용한다. MariaDB 코드의 존재로 OPEN-002의 플랫폼 DB 선택을 확정하지 않는다.

TASK-C는 기존 `mvp-ci.yml`을 보존한다. 따라서 PR에는 MVP 타입·빌드, Python 정적·단위 검사, 에이전트 설정 검사가 함께 표시된다. Python 검사는 `services/api/`만 대상으로 하며 `chatbot/`의 외부 LLM/DB를 실행하지 않는다. 비밀값이나 배포 권한은 CI에 추가하지 않았다.

TASK-D1 검증은 pytest 24개, Ruff, OpenAPI 스냅샷/프런트 타입 일치 검사, 생성물 변조 시 검사 실패, MVP 타입·빌드, npm audit 0건이다. 생성 계약의 원본은 실제 FastAPI 모델이며 아직 없는 도메인 API를 문서상 실행 가능한 경로로 내보내지 않는다. 기존 92개 기능 ID는 그대로다.
