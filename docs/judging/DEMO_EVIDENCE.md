# 시연·심사 증거 — J-002

2026-10-30 KST. 문서 소스 기준 main `4305fcf185cad41d3267c04255fef2ee5a23ca6e`. [공식 기준](RUBRIC.md)과 [현재 판정](SCORECARD.md)을 따른다. 문서 작성자는 공개 코드·CI와 운영자의 마스킹된 실행 요약을 읽었고 비밀·DB·서버에 직접 접근하지 않았다.

## 실행 SHA와 판정

| 증거 | 판정 | 범위·출처 | 제외되는 주장 |
|---|---|---|---|
| 과거 공통로그인·3CRUD | PASS, 과거 실행에 한정 | [승인된 P0 기록](../dev-prep/TASK_P0_APPROVED_LIVE_E2E.md), HTTP·MariaDB·핵심390/1280 각21단계 | 최신 main·전체92·운영 배포 PASS 아님 |
| 과거 규칙 기회 확인저장 | PASS, 실행 eebc1b42ef1fae7d97e53035378427943571b9f6 | [기회 실행 기록](../dev-prep/TASK_AI_OPPORTUNITY_ASSISTANT.md):10:38~10:40,390/1280 총17단계·편집/취소/동의/저장/재로그인/B격리 | 실제LLM·학과별 후보차이·마감순위 실증 아님 |
| 그 실행의 사후 정리 | INCOMPLETE | 캡처10토큰 폐기·saved/check0 확인, 전역세션 기대값 FAIL 및 미귀속1보존 | 전체세션0·원인확정·물리삭제 주장 금지 |
| 최신 재실행1 | FAIL | 운영자 요약: main25fa4cf95fcb599916514eb8f868e77e2b69ecdd, ANONYMOUS_CRUD; 생성 글 정리 확인 | 과거PASS로 덮지 않음 |
| 최신 재실행2 | FAIL | 같은main, 익명통과 후 RECRUITMENT_CRUD HTTP_OR_RESPONSE_FAILURE; 모집/세션 정리NOT_VERIFIED | 원인·정리완료·새브라우저PASS 추정 금지 |
| 문서기준main CI | PASS | 4305fcf의 Python/agent·웹·RAG·Docker공개프로필·프로토타입보존 검사6개 실제성공 | 실DB재실행·운영Docker·배포 아님 |
| 추가 가상5·프로필/액션/채널 | TESTED/PARTIAL | 단위/모의브라우저·PROCESS_MEMORY, 각 TASK 문서와 실제 소스 | MariaDB공유원장·현재운영권한·전체FR완료 아님 |
| 추가공지ack·운영제안·감사큐·로컬미리보기 | PR검증에 한정 | PR95/100/101/102 정확HEAD CI6개씩 성공, 각 전용/전체 단위 회귀 | 문서기준main에 모두 포함됐다고 가정하지 않음. 실제권한/원격시청0 |
| 공개HTTPS·심사용로그인 | NOT_RUN | [배포 준비](../dev-prep/TASK_DEPLOYMENT_PREPARATION.md), 준비 패키지 및 오프라인/CI 증거만 | 운영·외부공개 승인/실행 아님 |
| Lighthouse·실제LLM·발표/제출 | NOT_RUN/미확인 | 실제측정·호출·리허설·최종제출 확인 없음 | 성능90·AI5·발표 고득점·제출완료 가정 금지 |

최신 실패 요약은 root의 전달 근거이며 현재 원인을 단정할 공개 원문은 없다. 세 번째 자동 재실행·최신 브라우저는 이 문서 작성 시점 NOT_RUN이다. 후속 main/PR CI 진행은 별도이며 성공을 선반영하지 않는다.

## 직접 읽은 코드 근거

아래 행 번호는 문서 기준4305fcf의 소스다. 스키마·계약 존재와 실제 검증 수준을 구별한다.

| 항목 | 파일·시작행 | 확인 내용·한계 |
|---|---|---|
| 비밀번호 | [auth.py](../../chatbot/app/auth.py)16 | salt와PBKDF2 해시·상수시간 비교. 실제계정값 열람0 |
| HTTP 로그인·로그아웃 | [auth.py](../../services/api/app/api/v1/auth.py)45 | 공통 어댑터와 사전 제한 호출. 공급자/운영SSO 검증 아님 |
| 현재신원·소속·역할 | [bindings.py](../../services/api/app/integrations/platform_runtime/bindings.py)38 | 정확issuer/subject·승인audit pin·DEMO/current membership/role 확인 |
| 매 자원UOW 재검증 | [runtime.py](../../services/api/app/integrations/platform_runtime/runtime.py)105, [p0_runtime.py](../../services/api/app/db/p0_runtime.py)87 | 같은 트랜잭션에서 현재권한 다시검사 |
| 익명·모집 소유권 | [community_sql.py](../../services/api/app/repositories/community_sql.py)176·325 | actor 스코프·CAS, 공개취소숨김; 실제운영경합 전체 미검증 |
| 개인기록 소유권 | [opportunities_sql.py](../../services/api/app/repositories/opportunities_sql.py)169 | user+parent 범위. 전체준비목록 페이징은 미완 |
| 페이지·마이그레이션 | 위community_sql232·364, 위opportunities_sql102, [migration_runner.py](../../services/api/app/db/migration_runner.py)177 | 공개목록limit/cursor·CREATE-only장부. 서비스 전체성능 보증 아님 |
| 오류·private캐시 | [logging.py](../../services/api/app/core/logging.py)25·62 | 보호경로/root_path·안전한오류/no-store. 추가prefix 연결 전 별도검토 |
| FE 로그인·기회 | [App.tsx](../../apps/web/src/App.tsx)66·78·90 | 검증된auth.phase와generation으로 보호, 규칙도우미 연결 |
| 규칙과 향후LLM 구분 | [service.py](../../services/api/app/features/opportunity_matching/service.py)1, [planning_contract.py](../../services/api/app/features/opportunity_matching/planning_contract.py)1 | deterministic 규칙·미호출LLM 계약. 실제AI점수 근거0 |
| 실패 판정·정리 | [verify_p0_security.py](../../services/api/scripts/verify_p0_security.py)323·387·676·702 | 실패시NOT_VERIFIED, 모르는정리를성공으로표시하지않음 |
| 사진·단계 기록 | [runner.cjs](../../tests/e2e/src/runner.cjs)14·108·239 | opt-in 사진·단계별상태·실행조건. 파일존재는 별도확인 |

## CI와 사진의 공개 범위

- 기준main4305fcf의 check-runs6개를 GitHub에서 직접 확인했다. PR100/101/102의 단위 수치 및 CI는 해당PR HEAD에만 적용한다.
- 선택적 사진 경로 규칙은 `tests/e2e/.artifacts/<viewport>-<stageId>.png`다. 비밀번호 입력칸 마스크만으로 화면의 모든 개인자료가 정화된다고 보장하지 않는다.
- 이 문서 작업자는 실제 스크린샷/원문 보고서를 열거나 사진의 존재·마스킹 완료를 확인하지 않았다. 공개 제출본은 운영자가 개인표시·토큰·신원/감사UUID를 가린 사본만 검토해 제공한다. 사진이 미제공인 칸에는 사진 근거를 부여하지 않는다.
- 비밀파일·개별계정·접속주소·원시토큰·상담/성적·보호원문 로그를 본문/PR에 옮기지 않는다. 과거 승인16행과 기존 자료 보존은 관련 실행 기록의 범위다.

## README와 실행 증거의 대응

현재README 첫3은 익명게시글, 실명모집, 개인기회준비다. 과거불일치 지적은 해소됐지만 최신FAIL이므로 이 세 기능의 오늘 전체성공을 주장하지 않는다. [대본](DEMO_SCRIPT.md)은 운영자가 정확한main·정리·실행허용을 확인한 뒤 쓰는 제안이며 리허설NOT_RUN이다.
