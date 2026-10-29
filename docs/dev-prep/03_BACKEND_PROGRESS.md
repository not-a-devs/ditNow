# FastAPI 개발 상태와 승인 게이트

2026-10-30 KST · TASK-B. 관련 기준: NFR-SEC-004/005, NFR-PRIV-003, NFR-REL-004, NFR-OPS-001/002. 이 기반은 API-ID/COM/OPP의 공통 실행 환경이며 FR-AUTH-001 또는 학생 CRUD가 완료됐다는 뜻이 아니다.

| 범위 | 상태 | 증거 |
|---|---|---|
| FastAPI 공개 `/health`, `/api/v1/health` | IMPLEMENTED / TESTED | 실제 Uvicorn HTTP 요청 성공, 프로세스 종료 확인 |
| 공통 Pydantic 성공·오류 모델, 안전한 전역 예외, 요청 ID | IMPLEMENTED / TESTED | pytest의 정상·검증·404/405·도메인 오류·예상외 오류 검사 |
| 환경 설정·기본 거부 CORS·로그 최소화 | IMPLEMENTED / TESTED | 누락/부정 설정, 명시 origin, 비밀값 응답/로그 비노출 검사 |
| Python 의존성 | IMPLEMENTED / TESTED | Python3.13·uv0.13.6, pyproject.toml + uv.lock, `uv sync --locked` |
| Python CI | DOCUMENTED | TASK-C 별도 PR에서 실제 명령·GitHub 결과 확인 예정 |
| 인증/권한/DB/RLS·학생 업무 CRUD | BLOCKED / NOT_RUN | OPEN-002/003 및 도메인 승인 게이트 필요 |

로컬 검증: Ruff 정적 검사·포맷 통과, pytest 22개 통과, 앱 import/OpenAPI 생성 통과, MVP npm ci/typecheck/build 통과, 에이전트 설정·Git diff 검사 통과. TestClient의 httpx 사용 중단 예정 경고 1건은 라이브러리 경고로 남아 있다. 배포·프록시 로그·다중 계정/DB/부하 시험은 NOT_RUN이다.

독립 Codex 코드 리뷰에서 405의 Allow 헤더 누락을 발견했고 안전한 메서드 허용 목록으로 보존한 뒤 회귀 테스트를 통과했다. 사용자 요청으로 실행한 별도 Claude Code의 PR #11 설계 리뷰는 [후속 계약 PR #13](https://github.com/not-a-devs/ditNow/pull/13)에서 수용·보류 여부를 기록한다. AI 리뷰는 사람의 정책·권한 승인이 아니다.

실행법은 [API README](../../services/api/README.md), 현재 프런트 범위는 [MVP README](../../mvp/README.md)를 따른다. 이 문서의 TESTED는 명시된 공개 기반에 한하며 운영 환경 VERIFIED를 뜻하지 않는다.
