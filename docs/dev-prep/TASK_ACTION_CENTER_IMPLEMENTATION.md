# TASK-T — 홈 오늘 요약과 개인 알림함

상태: **PARTIAL / TESTED**, 전역 라우터·신규 앱 메뉴 미연결. 실제 인증·MariaDB 어댑터·원본 provider 어댑터·푸시 발송·운영 배포는 NOT_RUN/BLOCKED다. 세 FR 전체를 VERIFIED로 표시하지 않는다.

## 범위와 근거

FR-HOME-001(오늘 수업/과제/중요 공지/신청 상태 통합), FR-HOME-003(개인 알림함/읽음 처리), FR-NOT-005(알림 우선순위·중복 배포 정책)의 제한된 1차 구현이다. API-HOME/RBAC-HOME, TC-V1-HOME-001/003, TC-V1-NOT-005, NFR-SEC-001~007, NFR-PRIV, NFR-REL-001/002, NFR-DATA-001, NFR-UX-001을 연결한다.

- [통합 FRD](../v1-draft/02_FRD.md), [92개 추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv), [DB/API](../v1-draft/05_DB_API.md), [권한](../v1-draft/04_RBAC.md), [기존 FRD](../02_FRD.md)를 읽었다.
- FR-HOME-003은 공개 근거 부족(UNKNOWN), FR-HOME-001/FR-NOT-005는 INFERRED 설계 후보다. 학교 기존 기능과 동일하다고 주장하지 않는다.
- 공지 원장은 기존 `campus.NoticeRepository`와 `campus.policy`를 재사용한다. 공지 사본·두 번째 공지 원장·게시 권한을 만들지 않았다. 현재 접근 모델은 `notice_discussion.ports.CurrentAccess`를 재사용한다.

소유 파일은 `services/api/app/features/action_center/`, `services/api/tests/test_action_center.py`, `apps/web/src/features/action-center/`, 이 문서다. NAV/README/App/공통 client/router/OpenAPI/package/lock/DB 모델/migration/auth는 수정하지 않았다. `mvp/`를 참조·복사하지 않았다.

## 현재 API와 흐름

export router prefix는 `/action-center`이며 통합 시 `/api/v1` 아래 한 번 등록한다. 기본 앱에는 미마운트다. actor·서비스 dependency는 기본 503이다. 요청 body/query/header로 actor·recipient를 받지 않으며 추가 필드는 400이다.

| 경로 | 기능 | 완료/예외 기준 |
| --- | --- | --- |
| GET `/summary` | 현재 actor의 오늘 수업·7일 과제·최근 공지5·14일 기회 마감·읽지 않은 알림 수 | 섹션별 최대10, 원본 id·제목·시각·고정 링크·출처 라벨만 반환 |
| GET `/notifications?offset=&limit=20` | 본인 알림함, 최신순 | limit1~50, 현재 원본 권한이 없는 행은 숨기고 `next_offset`은 계속 전진 |
| POST `/notifications/{id}/read` `{expected_revision}` | 읽음 처리 CAS | 낡은 revision 409, 이미 읽음이면 현재 행 반환(멱등), 타인/권한 회수 404 |

수신 알림 생성은 라우트가 아닌 `ActionCenterService.deliver(NotificationEvent)`이며 승인된 outbox consumer만 호출한다. 푸시·문자·메일·외부 provider·AI 호출은 없다(`delivery=IN_APP_ONLY`).

## 정책 기본값(설계 기본값, 기관 정책 아님)

- 시각: clock은 aware여야 하며 아니면 503. 저장·응답은 UTC. 표시용 "오늘"은 고정 UTC+09:00(DST 없음) 하루 경계다.
- 정렬: 수업/과제/마감은 시각 오름차순(id 보조), 공지는 게시 시각 내림차순, 알림함은 `(created_at, id)` 내림차순. 응답에 `ordering=TIME_ASC_DEMO`, `priority_policy=NOT_DEFINED`를 명시한다. 학교 공식 중요도·우선순위를 만들지 않았다.
- 출처 라벨: `DEMO`(가상), `OFFICIAL_PUBLIC`(공개 자료 인용), `PLATFORM`(이 플랫폼에서 작성한 공지, 학교 시스템 기록 아님), `UNKNOWN`. 공지는 PLATFORM만, 그 외는 PLATFORM 불가. 불일치는 provider 계약 위반으로 503(fail closed).
- 링크: 원본 종류별 고정 섹션 경로(`/app/classrooms`, `/app/department`, `/app/opportunities`)만. 저장 URL·클라이언트 입력으로 만들지 않으며 FE도 동일 allowlist 외 응답을 거부한다.

## 원장·권한·DB 계약

- `Store.unit_of_work(actor_id)`는 검증된 공통 principal에 묶여 같은 트랜잭션에서 현재 active/DEMO 신원과 소속을 읽는다. 토큰 캐시 소속은 권위가 아니다.
- `SourceReader`는 provider-neutral 읽기 포트다. 통합 소유자가 academics(수강·시간표), online_learning(마감 학습), opportunities(저장 기회 마감) 포트에 위임해 구현하며 해당 모듈이 actor에게 보여 줄 범위를 넘지 않는 참조만 반환한다. 이 PR은 어댑터를 만들지 않았다.
- 중복 원천 이벤트: UNIQUE(recipient_id, source_type, source_id, event_key). 같은 이벤트 재전달은 기존 행을 반환하고 새 행을 만들지 않는다. 다른 event_key(예: 개정)는 별도 알림이다.
- 권한 회수: 목록·미읽음 수·읽음 처리·재전달 모두 원본 현재 접근을 다시 확인한다(공지는 `can_read_notice`+PUBLISHED/ARCHIVED, 그 외 `is_visible`). 회수된 경우 재전달도 기존 행을 반환하지 않는다. 행은 삭제하지 않는다.
- 읽음 CAS: `WHERE id AND recipient AND revision=expected AND read_at IS NULL`. 실패 시 409. 예외 시 모든 쓰기 rollback.
- 미읽음 수는 최근 100건을 현재 권한으로 필터한 값이며 100건 이상이면 `unread_capped=true`.
- 모든 응답·오류·미설치 503은 `Cache-Control: private, no-store`. recipient_id·event_key는 응답에 없고 제목·키·id·예외 원문은 로그에 남기지 않는다.

## 신규 화면

`apps/web/src/features/action-center/`의 `ActionCenterPage`는 실제 `requestData` 계약으로 요약·알림함을 읽는다. 각 영역에 접근 가능한 loading(`role=status`)/empty/error+다시 시도(`role=alert`)가 있다. 요청마다 이전 요청을 abort하고 최신 요청 응답만 반영한다. 응답은 키 집합·UUID·aware 시각·제목 길이·출처/링크 일치를 검증한다. 읽음은 서버 성공 응답 후에만 표시하고 409면 알림함을 다시 읽는다. 401/403이면 전체 개인 내용을 비우고 권한 재확인을 제공한다. App/메뉴에는 마운트하지 않았다.

## 수용 테스트·검증 기록 (2026-10-30, 기준 `18a7846`)

- TC-T-001: 현재 actor 범위 집계·오늘 경계(+09:00)·섹션 상한·공지 대상 필터·출처/링크 라벨.
- TC-T-002: 소속 회수 즉시 반영, 비활성/불일치/비DEMO 401/403, provider 계약 위반·naive clock 503.
- TC-T-003: 중복 원천 이벤트 멱등, 개정 이벤트 분리, 권한 회수 후 재전달·목록·읽음 거부, 삽입 실패 rollback.
- TC-T-004: 읽음 CAS·재요청 멱등·타 수신자 404·동시 갱신 409, 숨김 행 뒤 페이지 전진.
- TC-T-005: 기본 503·no-store·OpenAPI 미노출, actor/recipient 추가 필드 400, 예상외 오류 원문 미노출.
- TC-T-006(FE): 503 재시도, 텍스트 렌더·고정 링크·출처 라벨, 변조 응답 거부, 읽음 성공/충돌, 늦은 응답 무시, 401 비우기, StrictMode.

실행 결과: 전용 BE `pytest tests/test_action_center.py` 16 PASS, 전체 Python 695 PASS, `ruff check .`·`ruff format --check .` PASS. 전용 FE 7 PASS, 전체 웹 307 PASS, `typecheck`·`build`·`api:types:check` PASS. `check-feature-progress`(92, errors 0)·`check-agent-config` PASS.

테스트 fake는 RLock 직렬화 메모리 저장소이며 MariaDB 격리·잠금·UNIQUE를 입증하지 않는다. 실DB·실로그인·provider 어댑터·전역 라우터/메뉴 연결·실브라우저 E2E·`npm audit`은 NOT_RUN이다. 진행표/보드/NAV 갱신과 실제 활성화는 통합 소유자의 후속 태스크다.

### 독립 리뷰와 Unicode 제목 경계 보완

Codex B가 `216fc1d`를 읽기 전용으로 검토하고 전용 BE16/FE7을 각 1회 직접 통과했다. 현재 원본 접근·수신자 소유권·읽음 CAS/재요청·민감 본문 제외·private no-store·401/403 후 개인 화면 폐기·늦은 요청 취소를 확인했다. 실제 DB/운영 권한 검증이나 사람의 공식 승인은 아니다.

P2 재현: Pydantic은 이모지 150개 제목을 150 코드포인트로 허용하지만 FE의 기존 `String.length <= 200`은 UTF-16 300개로 거부하여 유효한 요약/알림함 전체를 오류 처리했다. 서버의 200 코드포인트 계약은 유지하고 FE는 UTF-16 400개 사전 상한과 `Array.from(title).length <= 200`을 함께 검사하도록 수정했다. 요약·알림함 양쪽에 200개 허용/201개 거부 회귀 2개를 추가했다. API/저장소/전역 화면 활성화는 변경하지 않았다.

보완 후 전용 FE9·타입 검사·빌드·Git diff 검사 PASS. 기존 BE도 보조 평면 문자 200개 허용/201개 거부를 별도 오프라인 실행으로 확인했다. 앞의 전체 Python695/웹307 기록은 원본 커밋 기준이며, 수정 HEAD의 전체 CI는 별도로 확인한다.

향후 실제 SourceReader 어댑터는 현재 actor 범위·시간창 필터와 시간/id 안정 정렬을 **LIMIT 이전에** 적용해야 한다. 섹션 최대10/공지5/미읽음 스캔100은 전체 학교 업무의 완전한 집계가 아니며, 현재 `unread_capped`는 제한된 미읽음 조회임을 나타낸다.
