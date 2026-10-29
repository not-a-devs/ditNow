# TASK-R — 공지 상세·개정 메타데이터와 학과 질문·댓글

상태: **PARTIAL / TESTED**, 전역 라우터·신규 앱 메뉴 미연결. 실제 인증·MariaDB 어댑터·파일 저장·공식 업무·운영 배포는 NOT_RUN/BLOCKED다. 두 FR 전체를 VERIFIED로 표시하지 않는다.

## 범위와 근거

FR-NOT-003(공지 상세·첨부·수정 이력·검색), FR-DEPT-006(학과 질문·댓글)의 제한된 1차 구현이다. API-NOT/API-CHAT, RBAC-NOT/RBAC-DEPT, TC-V1-NOT-003/DEPT-006, NFR-SEC-002/003/004/005/007, NFR-PRIV-003, NFR-DATA-001/003, NFR-REL-001/002, NFR-UX-001/003/005를 연결한다.

- [통합 FRD](../v1-draft/02_FRD.md), [92개 추적표](../v1-draft/09_FEATURE_TRACEABILITY.csv), [권한](../v1-draft/04_RBAC.md), [QA](../v1-draft/08_TEST_QA.md), [기존 FRD](../02_FRD.md)를 읽었다.
- 기존 학교 공지 조사 근거는 [공식 공지](https://www.dit.ac.kr/kr/index.php?pCode=notice), 2026-10-29 조사 존재 PARTIAL/처리 UNKNOWN이다. 이번 코딩 태스크에서는 학교 페이지를 새로 조사하거나 수집하지 않았다.
- 질문·댓글의 실제 학교 제공 여부는 INFERRED이며 독립 플랫폼의 승인된 시연 구현 범위다. 실명/익명 노출 정책을 확정하거나 학교 기능과 동일하다고 주장하지 않는다.
- 기존 `campus.NoticeRepository` 및 `campus.policy`를 재사용한다. 새 공지 원장·공지 게시 권한·알림 배포 경로를 생성하지 않았다.

소유 파일은 `services/api/app/features/notice_discussion/`, `services/api/tests/test_notice_discussion.py`, `apps/web/src/features/notice-discussion/`, 이 문서다. 공유 인증/DB/migration/lockfile/App/router/NAV/OpenAPI는 통합 소유자 영역으로 수정하지 않았다. 기존 `mvp/` 구현을 참조·복사하지 않았다.

## 현재 API와 흐름

export router prefix는 `/notice-discussion`이며 통합 시 `/api/v1` 아래 한 번 등록한다. 현재 기본 앱에는 미마운트다. actor와 서비스 dependency는 모두 기본 503이다. 모의 로그인·런타임 메모리 저장소·임의 DB 연결을 제공하지 않는다.

| 경로 | 기능·입력 | 완료/예외 기준 |
| --- | --- | --- |
| GET `/notices?q=&limit=25` | 현재 대상 범위의 최근 공지 최대50건 안에서 제목/본문 검색 | 단일 공지 원장 조회; 전체 검색 인덱스로 표시하지 않음 |
| GET `/notices/{notice_id}` | 기존 공지 원본의 상세+안전 첨부 메타+개정 메타 | 비대상/없는 공지404; 작성자/이전 본문/저장 URL/다운로드 미노출 |
| GET/POST `/departments/{department_id}/questions` | 현재 학생 소속 학과의 목록/질문 생성 | offset>=0/limit1~50; 제목160/본문4000; 생성 멱등 키 필수 |
| GET/POST `/departments/{department_id}/questions/{question_id}/comments` | 살아 있는 같은 학과 질문의 댓글 조회/생성 | 부모 권한·현재 상태 확인 후 질문 잠금; 타 학과/삭제된 부모404 |
| PATCH `/departments/{department_id}/items/{item_id}` | 본인 질문/댓글 변경, expected_revision 필수 | 서버 소유·부모 검증; 낡은 버전409, 타인404 |
| DELETE `/departments/{department_id}/items/{item_id}?expected_revision=` | 본인 글 tombstone | 내용/제목 최소화, claim 유지; 자식은 부모 삭제 후 조회·변경 불가 |

신규 화면은 공지 검색→기존 원본 상세/개정·첨부 메타, 학과 연결 후 질문 작성→댓글 조회/작성→본인 수정/삭제를 제공한다. 학과 UUID를 사용자가 직접 입력하는 화면은 만들지 않았다. 공통 앱이 승인된 현재 학과를 prop으로 공급하기 전에는 질문 영역을 사용할 수 없다고 표시한다. prop 변경 때 기존 선택/입력·요청을 폐기한다. API 성공을 받기 전에는 저장 성공을 표시하지 않는다. 동일 입력의 불확실한 실패 재시도는 멱등 키를 유지하고 입력이 바뀌면 회전한다. React StrictMode에서도 동작하며 전송 중복과 unmount 후 반영을 방지한다. 401/403이면 전체 영역을 비우고 현재 권한 재확인을 제공한다.

## 공통 원장·권한·DB 계약

`CurrentAccess`는 **기존 공통 원장을 같은 UOW에서 다시 읽은 값**이지 별도 사용자/소속 저장소가 아니다. actor id 일치·현재 활성·DEMO만 허용하며 질문/댓글은 현재 student 부여와 학과 membership 양쪽이 일치해야 한다. 이전 토큰의 학과를 권위로 쓰지 않는다. 실사용자 데이터 처리는 이 모듈로 승인하지 않는다.

DB 단일 소유자는 `Store/UnitOfWork`를 MariaDB로 구현한다. identity row를 먼저 잠그고 현재 역할/소속을 읽는다. 잠금 순서는 actor→질문 부모→item/claim이다. 댓글 생성·변경·삭제와 부모 질문 삭제는 같은 부모 잠금을 사용한다. 기존 공지 repository도 같은 연결·트랜잭션으로 공급하여 현재 원본/메타데이터의 혼합 버전을 방지한다. 읽기도 일관된 snapshot과 현재 자격 검증이 필요하다. 실제 MariaDB의 격리·잠금·권한은 테스트 fake로 입증되지 않는다.

필요 논리 레코드는 기존 notices/notice_attachments/notice revisions와 department_content의 질문·댓글, 공통 actor/학과 FK, 멱등 claims다. 이 PR은 SQL·migration을 작성하거나 실행하지 않았다. 질문/댓글은 `source_kind=DEMO`를 명시적으로 읽어야 하며 공개 응답은 owner UUID·실명·공식 답변 배지를 포함하지 않고 `is_mine`, `identity_display_policy=BLOCKED`만 제공한다. 익명 게시판의 보장과 동일하다고 표시하지 않는다.

생성 claim은 UNIQUE(actor,canonical path,key)와 검증한 payload SHA-256으로 구분하며 키는 대소문자를 정확히 보존한다. 같은 key/같은 body는 현재 글을 반환하고 다른 body는409다. 삭제 후 key replay는409이며 글을 부활시키지 않는다. claim+글은 같은 트랜잭션, 예외는 모두 rollback. 수정·삭제는 owner/학과/ACTIVE/revision 조건부 CAS로 처리한다. ACTIVE/DEMO를 필터한 후 `(created_at,id)` 안정 페이지를 적용한다. 보존 기간·신고/관리자 제재·일반 감사 정책은 별도 승인 전 차단한다.

## 첨부·이력의 안전한 제한

첨부는 filename/id/size만 있으며 경로·제어문자·URL·서명 URL·다운로드를 허용하지 않는다. 최대100개 메타데이터로 제한하며 실제 파일·검역·스토리지 권한·서명 URL은 미구현이다. 개정 이력은 현재 공지 revision 이하의 번호/시각/고정 이벤트 코드만 반환한다. 이전 비공개 초안·이전 본문·작성자·내부 사유는 반환하지 않는다. 이 메타데이터를 완전한 원본 보존/감사 구현으로 표시하지 않는다.

모든 응답·입력 오류·권한 오류·미설치503은 `Cache-Control: private, no-store`다. 사용자 본문·멱등 키·SQL/파일 경로·예외 원문을 로그에 기록하지 않는다. 프런트는 React text로만 렌더하고 성공 응답의 키·문맥·원천·길이를 검증한다. 원문 오류나 응답 속 신원을 화면에 표시하지 않는다.

## 수용 테스트·검증 기록

- TC-R-001: 기존 공지 원본·대상 범위 재사용, 안전 메타·현재 개정 필터, 작성자/URL/이전 본문 없음.
- TC-R-002: 학과 변경·정지·타 학과·타인 변경 거부, 부모 삭제 후 자식 접근 거부.
- TC-R-003: 생성 replay/다른 body 충돌/삭제 tombstone, CAS·부모 잠금·claim과 글의 rollback.
- TC-R-004: 미설치503·입력400·공통 오류/안전 로그/no-store·기본 앱 미마운트.
- TC-R-005: 신규 UI의 실제 client 호출 계약·StrictMode·오류 폼/키 유지·입력 변경 키 회전·응답 오염 거부·학과 변경 초안 폐기·권한 오류 비우기.

초기 실행: BE 전용14개·Ruff PASS, FE 전용7개·타입 검사 PASS, npm ci 취약점0. 보완 후 최종 결과는 후속 검증에서 갱신한다. 운영 DB·실 로그인·전역 메뉴/router 연결·실브라우저 E2E·부하·운영 배포는 NOT_RUN이다. UI/Protocol만으로 전체 FR을 IMPLEMENTED/VERIFIED 처리하지 않는다.
