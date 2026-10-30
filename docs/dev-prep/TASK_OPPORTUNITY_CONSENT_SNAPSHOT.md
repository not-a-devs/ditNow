# TASK-OPPORTUNITY-CONSENT-SNAPSHOT

Base: `e27e6b5`. Branch: `fix/opportunity-consent-snapshot-20261030`.

## 문제

`PreparationDraft.review()`는 저장된 준비 기록의 존재 여부(boolean)만 확인했다. 사용자는 "기존 메모·상태 유지" 또는 "새 기록 생성"에 동의하지만, 첫 `save()` 전에 기록이 삭제·재생성·수정되거나 새로 생길 수 있었다. 기존 코드는 바뀐 상황을 조용히 사용하여, 예전 동의로 초안 메모가 담긴 새 행을 만들 수 있었다.

## 수정 범위 (`PreparationDraft.tsx`만)

- 검토 성공 시 저장 행 스냅샷(존재 여부, `created_at`, `revision`)을 기록한다. 행이 없는 경우도 별도의 "검토됨(없음)" 스냅샷이며 "미검토"(`null`)와 구별한다.
- 첫 intent 생성 전 `save()`에서 최신 brief 확인과 최신 `listSaved` 이후 스냅샷을 실제 행과 비교한다. 있음→없음, `revision` 변경, `created_at` 변경, 없음→있음이면 `saveOpportunity`/`addCheck` 호출 0회, 동의 해제, 스냅샷 초기화, 편집 단계로 복귀, 편집 제목에 포커스, 한국어 재검토 안내를 표시한다. 사용자가 편집한 메모·항목은 유지한다.
- 초안 취소, 401/403 폐기, 공고 변경 시 스냅샷을 초기화한다. 새로 명시적 검토와 재동의가 있어야 저장한다.
- App/shared/auth/API/Backend/package/generated/NAV 변경 없음.

## 의도된 한계 (변경하지 않음)

- `intent.current`가 이미 있는 부분 재시도는 스냅샷을 비교하지 않으며 같은 batch/key/body/id/skip을 유지한다.
- 기존 `saveAttempted` 가드 유지: 불확실한 첫 PUT 이후 기록이 없으면 자동 재생성하지 않는다(안전 한계, 버그 아님).
- 기존 공고 변경 검사와 초안 보존 동작은 그대로다.
- 이 수정은 클라이언트의 첫 쓰기 전 재조회에서 관찰된 변경을 차단한다. 재조회 완료와 실제 서버 쓰기 사이의 원자적 조건부 갱신을 새로 보장하지 않는다. 그 보장은 별도 서버 계약·동시성 검증 범위이며 이번에 API를 변경하지 않았다.

## 요구사항 연결

- FR-OPP-002 / FR-OPP-004: 준비 기록 저장과 체크 추가는 검토한 기록 상태에 대한 명시적 동의 범위 안에서만 수행한다.
- FR-AI-002 / FR-AI-003: 규칙 기반 초안(AI 생성 아님)은 사용자 검토·동의 전 저장하지 않으며 편집 내용을 보존한다.
- NFR-SEC-002: 동의 이후 바뀐 맥락으로 개인 메모를 기록하지 않는다.
- NFR-REL-004: 부분 저장 재시도의 멱등 키·본문을 유지하고 자동 중복 생성을 하지 않는다.

## 테스트

`PreparationDraft.test.tsx`에 회귀 테스트 추가(목 기반 단위 테스트이며 실제 DB/브라우저 증거가 아님):

1. 기존 기록 검토 후 삭제 → 쓰기 0회, 동의 해제, 편집 단계·포커스, 초안 유지; 새 검토·재동의 후 정상 저장.
2. 기존 기록 검토 후 `revision` 변경 또는 `created_at` 변경(재생성) → 쓰기 0회.
3. 기록 없음 검토 후 기록 등장 → 쓰기 0회, 메모 유지.

기존 부분 재시도 테스트는 수정하지 않았다.

Claude는 제한 세션(Read/Grep/Glob/Edit/Write)에서 구현과 4개 모의 회귀를 작성했으며 명령 실행·네트워크·Git을 사용하지 않았다. 보고 비용 0.9215502달러, 83.8초, 정상 종료였다. Codex가 추가로 스냅샷의 `created_at` 누락·timezone 없는 응답을 동의 전에 거부하고 2개 모의 회귀를 추가했다. 실제 서버·DB·브라우저 등 라이브 시스템은 사용하지 않았다.

검증 결과는 다음 단계의 Codex 실행 결과와 PR의 정확한 HEAD 기준으로 기록한다. Claude 자체 테스트 실행은 NOT_RUN이다.

2026-10-30 Codex 직접 실행: `npm ci --ignore-scripts --offline` PASS/audit 0, `npx vitest run src/features/opportunity-matching` **55 PASS / 3 files** (초안 전용 24개 포함), `npm run typecheck`, `npm run build`, `git diff --check` PASS. 실제 HTTP·DB·브라우저·유료 LLM 호출은 NOT_RUN이다. 정확한 PR HEAD의 CI와 독립 리뷰는 별도로 확인한다.
