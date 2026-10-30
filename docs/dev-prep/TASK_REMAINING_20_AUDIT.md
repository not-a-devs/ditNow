# TASK-REMAINING20-AUDIT — 미구현 20행과 실제 코드 대조

- 확인일: 2026-10-30. 기준 main `e9229ecbbe6e491326ba9d75ef9d171a690ae1cc`.
- 범위: `06_FEATURE_IMPLEMENTATION_STATUS.csv`의 status=`NOT_IMPLEMENTED` 20행. CSV·명세·앱은 수정하지 않는다.
- 적용: spec-gap-review. 기존 92개 FR ID 보존. 관련 NFR-SEC-002/003, NFR-DATA-003, NFR-UX-001 및 각 TC-V1/기존 FR 테스트 기준을 유지한다.
- 방법: 실제 서비스·라우터·포트·FE·테스트 본문을 읽는 정적 감사. 이번 감사에서 테스트·서버·브라우저·DB·외부 모델 실행은 **NOT_RUN**. 아래 테스트 경로는 존재하는 회귀 근거이며 이번 재실행 결과가 아니다.
- 완료 조건: 20행 전부 대응, 기존 구현/실제 누락/미마운트 분리, 신규 구현 전에 재사용 후보 제안. 새 운영 정책·역할·가상 데이터 생성 없음.

## 1. 결론과 통합 경계

20행 모두를 무코드 상태로 해석하면 중복 개발한다. 15행에는 도메인 구현 또는 직접 재사용 가능한 부분 기능이 있다. 5행은 해당 완성 업무 흐름이 없으며, 아래에 표시한 기반 코드가 이를 대신하지 않는다. **20행 어느 것도 이번 감사만으로 IMPLEMENTED/VERIFIED로 승격하지 않는다.** 범위가 넓은 상위 FR과 부분 구현을 구분해야 한다.

기준 코드의 전역 공개 라우터는 `services/api/app/api/v1/router.py`, 조건부 P0 연결은 `services/api/app/factory.py`와 `api/v1/p0.py`다. P0 활성화 시 커뮤니티·모집·개인 기회·매칭은 `db/p0_runtime.py`의 실제 async 실행을 사용한다. 나머지 보호 도메인의 별도 router가 존재한다고 전역 mount나 SQL adapter가 존재하는 것은 아니다. 신규 웹 `apps/web/src/App.tsx`도 공개 검색·로그인·커뮤니티·모집·개인 기회 중심이며 아래 dormant 모듈들을 자동 import하지 않는다. 이후 root의 공유 통합 브랜치 변경은 이 고정 기준 감사에 포함하지 않았다.

## 2. 20행 추적표

공통 경로 접두사: BE=`services/api/app/features/`, BT=`services/api/tests/`, FE=`apps/web/src/features/`.

| FR | 기존 구현과 재사용 근거 | 테스트 근거 | 실제 남은 범위·판정 |
| --- | --- | --- | --- |
| FR-AUTH-003 | BE `profiles/service.py`, `router.py`; FE `profiles/index.tsx`. 자기 skills/interests/bio, CAS·멱등·정책 개정 검사 | BT `test_profiles_firstpass.py`; FE `profiles/index.test.tsx` | **부분 구현 존재**. 실명/소속/역할 편집 아님. 실제 current profile 정책·저장소 연결과 App mount 필요. 기본 dependency503 |
| FR-HOME-001 | BE `action_center/service.py:summary`; FE `action-center/index.tsx`. 수업·과제·공지·기회 마감 원본 참조 집계 | BT `test_action_center.py:test_summary_aggregates_current_references_in_bounded_windows`; FE `action-center/index.test.tsx` | **부분 구현 존재**. 실제 SourceReader/UOW·원본별 현재 권한·DB/전역 홈 연결 필요. 신청상태 전체·완전 집계 미완료 |
| FR-HOME-003 | 동일 모듈 inbox/mark-read, 개인 recipient 필터·revision CAS | BT `test_action_center.py:test_mark_read_cas_replay_and_other_recipient`; FE 읽음 후 summary 회귀 | **부분 구현 존재**. 실제 알림 원장/이벤트 공급·전역 연결 필요. OS push/email 없음 |
| FR-NOT-004 | action_center의 본인 읽음 표시를 기반으로 참고 가능 | 읽음 CAS 테스트는 있으나 이 FR 전체 테스트가 아님 | **업무 흐름 누락**. 공지 확인 요청·대상별 수신 확인·승인된 담당자 통계 없음. 개인 알림 read_at를 공지 열람 통계로 간주 금지 |
| FR-NOT-005 | action_center의 `(recipient,source_type,source_id,event_key)` dedupe, 시간순 집계 | BT `test_action_center.py:test_delivery_is_idempotent_on_duplicate_source_event` | **부분 구현 존재**. `HomeSummary.priority_policy='NOT_DEFINED'`, `ordering='TIME_ASC_DEMO'`. 공식 중요도/긴급도 정책·실제 배포 adapter 미확정 |
| FR-DEPT-003 | BE `channels/service.py`, `router.py`; FE `channels/`. 자유 채널 개설·참여·수정·보관·자기 탈퇴 | BT `test_channels_service.py`, `test_channels_http.py`; FE `channels/races.test.tsx` | **부분 구현 존재**. 실제 store/current grants와 전역 화면 미연결. 채팅 메시지 자체는 별도 campus 기능; 새 채널 원장 중복 금지 |
| FR-DEPT-004 | channels의 official request pending 생성·본인 조회 | BT `test_channels_service.py:test_owner_submits_official_request_pending_with_blocked_review` | **신청 부분만 존재**. 승인/반려 관리자 workflow·공식 badge 발급 없음. 기존 default channel을 학생 관리 경로로 변경 불가 |
| FR-OPP-002 | BE `opportunity_matching/service.py`; `repositories/opportunity_matching_sql.py`; `api/v1/p0.py` 실제 조건부 GET 연결; FE `opportunity-matching/` | BT `test_opportunity_matching_p0.py`, `test_opportunity_matching_service.py`; FE `opportunity-matching/*.test.tsx` | **실제 async API 연결 존재**. 현재 canonical 학과·학년/요청 관심사 기반 결정적 매칭. FE 전역 App 연결·현 HEAD 브라우저 검증은 별도 확인. 실제 외부 LLM 없음 |
| FR-COURSE-006 | BE `screen_sharing/` 현재 분반/발표자·signal·generation·budget 계약; FE `screen-sharing/media.ts` WebRTC lifecycle | BT `test_screen_sharing.py`; FE `screen-sharing/media.test.ts`, `index.test.tsx` | **부분 구현 존재**. 실제 broker/SFU/분반 repository·전역 mount·실캡처/장치 호환 없음. 테스트 fake는 runtime 저장소가 아님 |
| FR-ACA-002 | BE `academics/service.py` enroll/drop/transcript/학적 request; FE `academics/CoursesPanel.tsx`, `RequestsPanel.tsx` | BT `test_academics_service.py`, `test_academics_concurrency.py`, `test_academics_http.py`; FE `academics/` tests | **상위 FR 부분 구현 존재**. 명시 DemoAcademicPolicy 없으면503. 공식 학적/성적·증명서 효력·실DB/승인 원장 미연결; 새 학사 도메인 복제 금지 |
| FR-CAMP-002 | BE `campus_travel/service.py:calculate_travel`; FE `campus-travel/`. offset 있는 일시+사용자 입력 이동분으로 초 단위 여유 계산 | BT `test_campus_travel.py`; FE `campus-travel/index.test.tsx` | **독립 계산 구현 존재**. 실제 경로/지도 추정·개인 시간표 자동 연결 없음. `build_travel_router(enabled=False)` 기본 비활성·전역 미마운트 |
| FR-ADM-001 | 기존 canonical identity/role 원장은 권한 검증용 기반일 뿐 | 공통 P0 access tests는 관리자 UI 테스트가 아님 | **관리 업무 누락**. 사용자·조직·역할 부여/회수·공식 채널 승인 관리자 API/FE 없음. 학생 요청만으로 관리자 권한 발급 금지 |
| FR-ADM-002 | 공통 audit_logs 및 개별 서비스 audit 계약은 기반 | 도메인 rollback/audit tests가 운영 처리 검증을 대신하지 않음 | **관리 업무 누락**. 공지/게시물/신고 감사 검색·처리 workflow와 담당자 UI 없음. 익명 작성자 조회 권한을 발명하지 않음 |
| FR-AI-001 | action_center summary의 현재 원본·시각·링크를 행동 후보 입력으로 재사용 가능 | BT `test_action_center.py` 집계/현재 권한/숨김 원본 tests | **기반 부분 존재**. 오늘의 행동 브리핑 생성·우선순위·실제 개인 원장/전역 연결 미완료. 요약 데이터가 존재한다고 AI 브리핑 완료 아님 |
| FR-AI-002 | matching `brief()`의 원본 필드 근거·누락 조건·준비 단계; FE `PreparationDraft.tsx` 명시 확인 후 기존 개인 기회 API 저장 | BT `test_opportunity_matching_service.py`, `test_opportunity_matching_http.py`; FE `PreparationDraft.test.tsx` | **결정적 구조화 구현 존재**. 원본 없는 주관/URL/마감 발명 없음. LLM 요약 생성은 없으며 전역 연결·실제 신규 수직 검증 별도 |
| FR-AI-003 | matching의 관심 키워드/종류 reason code·명시 점수; RecruitmentReferenceReader seam | BT `test_opportunity_matching_service.py`; FE `opportunity-matching/` tests | **기회 관련도 부분 존재**. 실제 P0 runtime의 모집 참조는 NOT_CONNECTED. 모집 공고/활동 전체 추천 및 모델 추천 완료 아님 |
| FR-ATT-003 | academics의 teacher open_session/student check_in 인증번호·기간·시도상한·현재 수강 검사 | BT `test_academics_service.py:test_check_in_code_attempts_persist_and_limit`, `test_check_in_window_and_closed_session`; FE `academics/AttendancePanel.tsx` | **시연 인증번호 부분 존재**. 캠퍼스락/블루투스 장치·공식 출결 연동 없음. 학교 출석 판정/실DB 미검증 |
| FR-ATT-004 | 기존 auth/me는 현재 신원 기반일 뿐 학생증 발급 계약 아님 | 전용 모바일학생증 테스트 없음 | **업무 흐름 누락**. 학생증 DTO/유효성/폐기·UI 없음. 가상 표시는 가능하나 공식 학생증/신분 증명으로 표현 금지 |
| FR-ADM-003 | 각 admissions/library/student_life 서비스에 업무 actor/권한 protocol 있음 | 해당 도메인 권한 거부 unit tests 존재 | **통합 역할 운영 누락**. 입시관리자·사서·상담자·생활관 역할 발급/회수·조직범위·current bridge 연결 없음. 개별 fake grant는 실제 권한 부여 증거 아님 |
| FR-ADM-004 | 공통/도메인 DTO에 DEMO/OFFICIAL_PUBLIC/PLATFORM/UNKNOWN 표시, public campus 출처·matching provenance, FE 출처 문구 | BT `test_academics_service.py:test_provenance_separates_official_demo_and_unknown`, `test_public_campus.py`; FE 공개/기회 guard tests | **표시 기반 부분 존재**. 중앙 출처 편집·승인·원본 변경 이력 관리 도구는 없음. 출처 라벨이 관리 workflow 완료를 뜻하지 않음 |

## 3. 다음 작업 제안 — 새 모듈보다 기존 구현 연결

1. **이동 여유 계산을 기존 캠퍼스 화면에 연결:** 기존 순수 계산/입력 검증/FE를 재사용한다. 공식 이동시간·지도 추정 없이 사용자가 두 일시와 예상 이동분을 직접 입력하는 시연 범위. 보호 원장·DB·새 role 불필요. root의 공통 App/router 단일 소유로 mount하고 offset/동시각/중첩·오류·모바일 회귀를 유지한다. 새 계산기를 만들 필요가 없다.
2. **모바일학생증의 명확한 비공식 시연 카드:** 실제 누락의 최소 독립 UI 후보. 기존 auth/me의 현재 메모리 세션만 표시하고 별도 계정/권한/DB 생성하지 않는다. "가상 시연·학교 학생증 아님" 상시 표기, QR/바코드·학번 유추·검증 가능한 신분 증명 기능은 포함하지 않는다. 로그아웃/401/계정 전환 즉시 폐기. 구체 구현 범위는 root 승인 후 착수한다.

공지 통계·관리자 운영·공식 채널 승인은 역할/개인정보/집계 정책이 엮이므로 단순 mock badge나 학생 권한으로 대체하면 안 된다. 사용자 요청의 가상 구현과 실제 운영 권한은 구분한다. 현재 계정·모델·DB·배포 승인 범위를 확대하지 않는다.

## 4. 감사 검증과 남은 일

- CSV `status=NOT_IMPLEMENTED` 정확히 20행을 읽고 표 20개 FR과 일대일 대응했다. CSV는 읽기만 수행했다.
- 위 source/test 경로는 고정 기준 checkout에서 확인했다. 핵심 근거 24개 경로 존재 검사 PASS, 표의 20개 FR/CSV 행 대응 PASS, `node scripts/check-feature-progress.mjs` 92개 ID·오류0 PASS(기존 CSV 67 PARTIAL/20 NOT_IMPLEMENTED/5 BLOCKED 유지), `git diff --check` PASS.
- 이번 감사의 자동 기능 테스트·실DB·미디어·브라우저·공개 HTTPS·운영 배포: **NOT_RUN**. 기존 다른 태스크의 실제 PASS 증거를 이번 재실행으로 주장하지 않는다.
- NAV 및 진행 CSV 수정은 root 소유라 수행하지 않았다. root가 각 행을 PARTIAL/DOCUMENTED/TESTED 등 계층 상태로 정정할 때 전체 업무 완료 여부와 runtime mount 여부를 별도로 보존해야 한다.
