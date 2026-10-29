# TASK-K — 커뮤니티 협업(익명 댓글·북마크·검색·신고 요청, 가상 스터디/동아리·팀 활동 공간) 1차 구현 기록

- 작성일: 2026-10-30
- 브랜치: `feat/collaboration-firstpass-20261030` (독립 worktree `C:/DIT CSW/ditNow-collaboration`, 기준 main `8bb0e7f`)
- 상태: `review` — 기능 패키지·단위/HTTP 계약 테스트·프런트 Vitest 완료. **공통 앱 미연결(라우터 미마운트), 인증·DB 미연결, 실제 DB·브라우저 미실행(NOT_RUN).**
- 근거 문서: `docs/02_FRD.md` §FR-COM-001~003, `docs/04_POLICY_RBAC.md` §2·3·8, `docs/05_DATA_MODEL.md`(reports), `docs/v1-draft/03_NFR.md`, `docs/v1-draft/04_RBAC.md`(RBAC-COM), `docs/v1-draft/05_DB_API.md`(API-COM), `docs/v1-draft/08_TEST_QA.md`(TC-V1-X02), `docs/v1-draft/09_FEATURE_TRACEABILITY.csv`, `docs/v1-draft/10_AI_TASK_RULES.md`, `docs/v1-draft/13_P0_SERVER_DB_RLS_CONTRACT.md`, `docs/dev-prep/TASK_COMMUNITY_IMPLEMENTATION.md`.
- `mvp/` 소스는 읽거나 복사하지 않았다. 공통 router/factory/auth/DB models/migrations/pyproject/uv.lock/package/App/NAV/README/workflow, `features/community/**`는 수정하지 않았다.

## 1. 범위와 추적

| 요구사항 | 이번 구현 | 차단(BLOCKED)/범위 외 | TC |
| --- | --- | --- | --- |
| FR-COM-002 익명 댓글/좋아요/북마크/검색 | 익명 댓글 CRUD(작성·목록·수정·삭제), 개인 북마크(추가·해제·목록), 공개 projection 검색 | **좋아요 미구현**(이번 요청 범위 외, NOT_IMPLEMENTED) | TC-V1-COM-002 |
| FR-COM-003 신고·차단·제재·이의신청 | **신고 요청만**: 사유 enum 접수, 본인 접수 내역 조회 | 운영자 열람·익명 작성자 매핑·제재 실행·사용자 차단·이의신청 **BLOCKED_POLICY**(라우트 없음) | TC-V1-COM-003(부분) |
| FR-COM-006 스터디·동아리 개설·참여 | 가상(USER_DEMO/DEMO) 모임 개설·목록·상세·참여 요청·모임장 승인/거절·탈퇴 | 공식(OFFICIAL_PUBLIC)/출처 미상(UNKNOWN) 동아리 가입 **BLOCKED_POLICY**(안내만), 모임장 위임·모임 종료 정책 미정 | TC-V1-COM-006 |
| FR-COM-007 팀원 확정 후 팀 대화·활동 공간 | 모임 참여자 전용 활동 기록(작성·목록·삭제), 실시간 아님 | **모집(FR-COM-005) 팀의 공간 BLOCKED_CONTRACT** — COM-005 지원·승인 API가 community에 없으므로 중복 작성하지 않음 | TC-V1-COM-007(부분) |
| 교차 | 익명↔실명 교차 식별자 없음 | — | TC-V1-X02(단위 수준) |

NFR: NFR-SEC-001(보호 API 인증 필수·미설정 503), NFR-SEC-002(서버 소유권/부모 scope), NFR-SEC-005(길이·제어문자·추가필드 거부, HTML은 텍스트), NFR-PRIV-001(익명 응답 식별자 제외), NFR-REL-001(영속성 — **BLOCKED**), NFR-REL-003(정원 원자성 — Protocol+fake만), NFR-REL-005(페이지네이션·이름 배치 조회), NFR-UX-001(로딩/빈/오류/503/재시도).

### 기존 community와의 관계(중복 금지)
- 익명 글 원본·CRUD는 community 소유. 이 기능은 **글 ID만 재사용**하고, UOW가 community의 공개 projection 행 타입 `AnonymousPostPublicRow`(작성자 필드 없음)로만 글을 읽는다. 비공개 원장(`anonymous_posts_private`)을 응답 경로에 join하지 않는다.
- `comment_count`는 community 공개 projection의 필드다. 댓글 쓰기/삭제와 같은 트랜잭션에서 갱신하는 것은 DB 어댑터 의무로 Protocol에 명시했다(community 코드 미수정).
- FR-COM-005 지원·승인은 community의 도메인 규칙만 있고 API가 없다. 모집 지원/승인을 여기서 다시 만들지 않았다.

## 2. 변경 파일 (모두 소유 범위)

- `services/api/app/features/collaboration/`
  - `domain.py` — 상수(모두 시연 설계 기본값), enum, 레코드, `ParticipationGrant`/`GroupGrant`, aware UTC 강제, 안전 URL·출처 정규화.
  - `idempotency.py` — scope `(actor, POST, canonical path(/api/v1+구체 부모 ID), key)` + payload SHA-256, replay/409/타 scope 500 판정.
  - `ports.py` — `CollaborationStore.transaction(actor_id)` / `CollaborationUnitOfWork` Protocol과 원자성·CAS·행 잠금·tombstone 의무.
  - `schemas.py` — 요청(`extra=forbid`)/응답 DTO.
  - `service.py` — 권한·scope·멱등·CAS 판정.
  - `router.py`, `__init__.py` — `create_collaboration_router(CollaborationDependencies)`, 기본 `router`(503), 오류 응답까지 `Cache-Control: private, no-store`.
- `services/api/tests/test_collaboration_support.py`(테스트 전용 fake UOW), `test_collaboration_http.py`, `test_collaboration_service.py`.
- `apps/web/src/features/collaboration/` — `index.tsx`(default export), `AnonymousPanel.tsx`, `MyActivityPanel.tsx`, `GroupsPanel.tsx`, `ui.tsx`, `api.ts`, `guards.ts`, `types.ts`, `api.test.ts`, `index.test.tsx`.
- `docs/dev-prep/TASK-K_IMPLEMENTATION.md`(이 문서).

## 3. API 계약 (미마운트; root가 `/api/v1` prefix로 include 예정)

| 메서드·경로 | 동작 | 주요 오류 |
| --- | --- | --- |
| `GET /search/anonymous-posts?q&limit&offset` | 활성 익명 글 공개 projection 검색(q 2~50자) | 400, 401/403 |
| `GET /anonymous-posts/{post_id}/comments` | 활성 댓글(오래된 순), `is_mine` 서버 계산 | 글 비활성/없음 404 |
| `POST /anonymous-posts/{post_id}/comments` `{body}` + `Idempotency-Key` | 201(replay 201 + `Idempotent-Replayed: true`) | 1~1000자, 같은 키 다른 본문 409, 삭제 후 replay 404 |
| `PATCH /anonymous-posts/{post_id}/comments/{comment_id}` `{revision, body}` | 본인만 | 타인·다른 부모 404, revision 409 |
| `DELETE …/comments/{comment_id}?revision=` | 본인만, 본문 비운 tombstone | 404/409 |
| `GET /me/bookmarks`, `PUT/DELETE /me/bookmarks/{post_id}` | 본인 북마크(자연키 멱등); 비활성 글은 목록에서 제외 | 비활성 글 추가 404 |
| `POST /reports` `{target_type, target_id, reason}` + `Idempotency-Key` | 사유 enum만(spam/abuse/hate/sexual/privacy/misinformation/other), 상태 `submitted` | 자유 서술 필드 400, 본인 대상 409, 동일 대상 중복 409, 대상 비노출 404 |
| `GET /me/reports` | 본인 접수 내역만 | — |
| `GET /groups?kind&q`, `GET /groups/{id}` | 공개(open) 모임, 출처·`policy_basis=DEMO_DESIGN_DEFAULT`, 모임장 활동명, 내 멤버십 | 없음 404 |
| `POST /groups` + `Idempotency-Key` | 개설자=모임장, `origin=member_created`, `source=USER_DEMO` | 서버 소유 필드 주입 400, 정원 2~30 |
| `POST /groups/{id}/join-requests` + `Idempotency-Key` | open→즉시 active(좌석 필요), approval→pending | 중복/거절 후 재요청/정원 초과/공식·미상 출처 409 |
| `GET /groups/{id}/join-requests` | 모임장만, 대기 요청 + 활동명 | 비모임장 404 |
| `POST /groups/{id}/join-requests/{mid}/decision` `{decision, revision}` | 모임장만, 승인 시 좌석 확인 | 다른 모임의 요청 404, revision/상태 409 |
| `POST /groups/{id}/membership/leave` `{revision}` | 참여자/대기자 탈퇴·취소 | 모임장 409(위임 정책 미정), 비참여 404 |
| `GET/POST /groups/{id}/space/posts`, `DELETE …/{post_id}?revision=` | 활성 참여자 전용 활동 기록(실명 활동명) | 비참여·대기·탈퇴 404, 타인 삭제 404, revision 409 |

공통: 응답 `SuccessResponse`, 오류 `ErrorResponse`. 성공·오류 응답 모두 `Cache-Control: private, no-store`(전용 route class).

## 4. 보안·정합성 규칙과 테스트 매핑

| 규칙 | 구현 | 테스트 |
| --- | --- | --- |
| 기본 auth/store 미설정 503, 전역 router 미마운트 | 기본 의존성 `UNAVAILABLE` | `test_default_router_fails_closed_with_private_503` |
| 인증 판정이 저장소보다 먼저 | 서비스 의존성이 actor에 의존 | `test_auth_is_resolved_before_store` |
| 권한은 서버 주입 actor + 현재 UOW grant로만 | actor는 user_id만, 참여 자격/모임 역할은 트랜잭션 내 재조회 | `test_revoked_participation_is_403_everywhere`, space 탈퇴 후 404 |
| 본인/부모 scope·인가 선행·404 비노출 | 댓글↔글, 요청↔모임, 기록↔모임 대조; 타인 자원 404 | update/decision/space 테스트 |
| 멱등 scope actor+method+canonical path+key+payload hash, 같은 트랜잭션 | `claim`이 자원과 같은 UOW | `test_comment_idempotency_replay_conflict_and_scope`, `test_scope_is_actor_method_canonical_path_and_key` |
| replay 시 현재 권한 재검증 | grant 확인이 claim보다 먼저 | `test_replay_after_permission_revoked_is_refused`, space 탈퇴 후 replay 404 |
| 삭제 후 tombstone 보존(부활 금지) | 소프트 삭제·본문 제거·claim 유지 | `test_replay_after_delete_is_404_tombstone_not_resurrected`, space tombstone |
| optimistic revision/CAS | `cas_*` + 서비스 사전 비교 | stale revision 409 다수 |
| 실패 시 원자 롤백(claim 포함) | fake 스냅샷 롤백 | `test_report_failure_rolls_back_claim`, `test_failed_write_rolls_back_claim_and_counter` |
| 동시성(정원·같은 키) | 그룹 행 잠금 계약 + fake RLock | `test_concurrent_joins_never_exceed_capacity`, `test_concurrent_same_key_creates_one_comment` |
| 타 scope claim 반환 시 실패닫힘 | 500 | `test_adapter_returning_foreign_claim_fails_closed` |
| 익명 응답 식별자·별칭 없음, 교차 추론 금지 | DTO에 필드 자체 없음 | `test_comment_is_anonymous…`, `test_anonymous_and_real_name_zones_share_no_identifier` |
| 신고 사유 enum만, 관리자/제재 라우트 없음 | `extra=forbid`, 라우트 미제공 | `test_report_reason_enum_only…`, `test_no_operator_review_sanction_block_or_appeal_routes` |
| Aware UTC | 서버 시계 naive면 500, 확인일 UTC 정규화 | `test_naive_server_clock_fails_closed`, `test_normalize_source…` |
| 안전 외부 URL, OFFICIAL_PUBLIC은 URL+확인일 필수, UNKNOWN/DEMO 구분 | https·호스트·자격증명/fragment/제어문자 금지, 미래·naive 확인일 거부 → UNKNOWN 강등; 비공식 종류는 링크 없음 | `test_catalog_source_is_normalized_fail_closed`, `test_safe_public_url` |
| 학교 정책과 가상 demo 정책 분리 | `policy_basis=DEMO_DESIGN_DEFAULT`; 가입은 DEMO/USER_DEMO만 | catalog 가입 409 테스트 |

**원자성 주의:** 위 원자성·동시성 결과는 Protocol 계약과 **테스트 전용 fake**(전역 RLock + 스냅샷 롤백)로 확인한 것이다. MariaDB InnoDB의 실제 트랜잭션·`SELECT … FOR UPDATE`·UNIQUE 경합·GRANT는 **검증하지 않았다(NOT_RUN)**.

## 5. 프런트 동작 원칙

- 공유 `requestData<T>('/feature/path')`만 사용; `/api/v1`은 공유 client가 붙이므로 BASE를 추가하지 않는다. 실제 client + fetch stub으로 19개 엔드포인트 최종 URL이 `/api/v1` 한 번임과 절대 base 설정을 회귀 검사한다. `%2F` 등 경로 조작 ID는 공유 client가 요청 전 거부한다.
- 모든 응답은 `guards.ts` 런타임 guard 통과 후에만 상태에 들어간다. 익명 영역(글 요약·댓글·북마크·신고)은 **정확한 키 집합**을 요구해, 신원 필드가 섞이면 렌더링하지 않고 "서버 응답 형식을 확인할 수 없습니다"를 표시한다.
- 401/403은 어느 패널에서든 루트로 올려 **모든 개인 화면을 언마운트**하고 부모 안내만 표시한다(다시 시도 시 새 세션으로 재마운트).
- 로딩/503(연결 준비 중)/빈/오류(요청 ID)/재시도. 실패 시 폼 값 유지, 같은 의도 재시도는 같은 키, 입력 변경 시 키 회전, 성공 시 리셋. 북마크·신고·참여 상태는 서버 응답으로만 바뀌며 실패 후 성공 문구를 표시하지 않는다.
- 서버 문자열은 React 텍스트로만 렌더링, 오류 메시지는 고정 한국어 문구(서버 message 미표시). 링크는 OFFICIAL_PUBLIC + 안전 https + 확인일일 때만.
- 새 인증·가짜 로그인 저장소·localStorage·mock fallback 없음. **전역 `App.tsx`에 미마운트 — 타입체크·RTL로만 검증했고 실제 브라우저·DB 동작은 확인하지 않았다.**

## 6. 실제 검증 (2026-10-30, 이 worktree)

| 위치 | 명령 | 결과 |
| --- | --- | --- |
| `services/api` | `uv sync --locked` (uv `C:/DIT CSW/ditNow-python-tools/Scripts/uv.exe`, CPython 3.13.3) | 성공 |
| `services/api` | `uv run --locked ruff check .` | `All checks passed!` |
| `services/api` | `uv run --locked ruff format --check .` | `75 files already formatted` |
| `services/api` | `uv run --locked pytest -q` | **473 passed**(collaboration 76 포함, 기존 테스트 무수정), 경고 1(httpx/starlette deprecation) |
| `apps/web` | `npm ci` | 성공, 0 vulnerabilities |
| `apps/web` | `npm run api:types:check` | `New web API types match the public server snapshot.` |
| `apps/web` | `npm run typecheck` | 오류 없음 |
| `apps/web` | `npm test` | **1차 실행: 173 중 4 실패** — 내 stub 버그 2건(수정함) + `classrooms/index.test.tsx` 2건(타 소유, 미수정). classrooms+collaboration만 실행 시 42 passed, **전체 재실행 12 files / 173 passed**. classrooms 2건은 전체 병렬 부하 시 타이밍 의존으로 흔들리는 것으로 보이며 원인 미확정(root 확인 필요) |
| `apps/web` | `npm run build` | 성공. 단 `App.tsx`가 collaboration을 import하지 않아 **번들 미포함** |
| `apps/web` | `npm audit --audit-level=moderate` | 0 vulnerabilities |
| 루트 | `node scripts/check-agent-config.mjs` | PASS(8 mirrored skills) |
| 루트 | `node scripts/check-feature-progress.mjs` | errors [] (진행표 CSV는 소유 외라 미수정) |
| 루트 | `git diff --check`(staged) | 커밋 전 실행 결과는 PR 본문 기록 |

적용 TC: TC-V1-COM-002(댓글·북마크·검색, 단위/HTTP), TC-V1-COM-003(신고 요청만, 단위/HTTP), TC-V1-COM-006/007(가상 모임·활동 공간, 단위/HTTP), TC-V1-X02(익명/실명 교차, 단위 수준). **브라우저 2계정·실DB 시나리오는 모두 NOT_RUN.**

## 7. 미검증 / 게이트 / 차단 (root·사람 승인 필요)

1. **라우터 마운트**(root): `app.include_router(create_collaboration_router(deps), prefix="/api/v1")`. 마운트 시 OpenAPI 스냅샷·foundation 경로 단언·프런트 생성 타입 갱신. community 라우터의 `/anonymous-posts/{post_id}`와 경로 충돌 없음(하위 `/comments`, 검색은 `/search/...`).
2. **인증 BLOCKED**: 공통 인증이 `CollaborationActor(user_id)`를 주입해야 함(미인증은 `None`→401). 역할/자격은 actor에 싣지 않고 UOW가 트랜잭션 내 재조회.
3. **DB BLOCKED**: MariaDB 테이블(`anonymous_comments`, `bookmarks`, `reports`, `collab_groups`, `group_memberships`, `group_space_posts`, `idempotency_records`)·마이그레이션·어댑터 없음. 요구사항은 `ports.py` 주석. 실제 DB 접속·스키마·계정·GRANT·migration은 시도하지 않았다(root/DB 단일 소유).
4. **멱등 기록 보존 기간/TTL**, 신고 남용 제한(NFR-SEC-006 rate limit) — DB/공통 미들웨어 담당 결정.
5. **신고 처리 정책(OPEN-009, RBAC §3-5)**: 운영자 열람·익명 작성자 매핑 조회·감사 로그·제재·차단·이의신청·본인 신고 규칙 — 승인 전 라우트/UI 없음.
6. **공식 동아리**: 학교 동아리 등록·가입 규정 미확인 → OFFICIAL_PUBLIC/UNKNOWN 모임은 안내만. 카탈로그 시드는 이 기능에서 만들지 않음.
7. **모집 팀 공간(FR-COM-007의 COM-005 연계)**: COM-005 지원·승인 API가 생기면 UOW의 `group_grant`와 같은 방식의 팀 grant로 연결 예정.
8. **좋아요**(FR-COM-002) 미구현, 실시간 팀 대화 미구현(목록 새로고침 방식).
9. CORS: 교차 출처 배포 시 PUT/PATCH/DELETE·`Idempotency-Key` 허용 여부 root 결정.
10. 시연 기본값(댓글 1000자, 정원 2~30, 검색 2~50자, 신고 사유 목록)은 승인된 정책 값이 아니다.

## 8. 상태 구분

- **IMPLEMENTED(부분, 미연결)**: FR-COM-002(좋아요 제외)/003(신고 요청만)/006/007(모임 공간) 기능 패키지·프런트 소스.
- **TESTED(unit/HTTP, fake)**: 6절 백엔드 76 + 프런트 collaboration 33.
- **BLOCKED**: 인증·DB·마운트, 운영자 신고 처리·제재·차단·이의신청, 공식 동아리 가입, 모집 팀 공간.
- **NOT_RUN**: 실제 MariaDB, 2계정 브라우저 E2E, 390/1280 반응형, CI(이 세션은 결과 미확인).
- 전체 FR **VERIFIED 아님**. 진행표(`06_FEATURE_IMPLEMENTATION_STATUS.csv`)·보드·NAV는 소유 외라 root가 갱신한다.

## 9. 다음 실행 가능 태스크

1. root: 라우터 마운트 + OpenAPI/타입 갱신 + 진행표·보드 갱신 + `App.tsx` 연결.
2. 인증 담당: actor 공급 의존성. DB 담당: 7절 테이블·UOW 어댑터와 실DB 통합 테스트(동시 가입·같은 키 경합 포함).
3. 정책 승인 후: 신고 처리/제재(FR-COM-003 나머지), 좋아요, 모집 팀 공간 연결.
