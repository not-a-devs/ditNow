# 강의실 1차 서비스

`TASK-G-CLASSROOMS`의 공급자 독립 모듈이다. 기본 앱에 라우터를 연결하지 않으며 공통 인증/현재 수강·담당 교수/트랜잭션 저장소 어댑터가 승인·설치되지 않으면 `get_classroom_actor`, `get_classroom_service`는 `503 UNAVAILABLE`이다. 클라이언트 헤더·본문의 user_id/role을 신뢰하는 인증, 런타임 메모리 저장소, 실제 DB·파일 업로드는 제공하지 않는다.

라우터 소유자가 `router`를 `/api/v1` 아래 연결할 수 있다. 등록 후 `/api/v1/classrooms`가 분반 목록이며, 현재 공개 OpenAPI 스냅샷에는 이 미연결 모듈의 경로를 추가하지 않는다. 등록 시 공통 OpenAPI 스냅샷·생성 타입·라우트 테스트를 별도 갱신해야 한다.

| 모듈 상대 경로 | 데이터/권한 | 오류 |
| --- | --- | --- |
| GET `/classrooms?limit=25` | 현재 승인된 본인 분반 최대 100개 | 미설치 503, limit 부정 400 |
| GET `/classrooms/{offering_id}` | 현재 수강생/담당 교수만 자료·과제·조회 가능 질문·본인 제출 | 미수강/취소/다른 분반 403 |
| POST `/classrooms/{id}/questions` | 학생 텍스트 1~2000자; 교수에게만 보기 | `Idempotency-Key` 16~100 영숫자/하이픈 필요; 같은 키 다른 텍스트 409 |
| POST `/classrooms/{id}/questions/{qid}/answer` | 담당 교수; text + expected_revision | open 이외/버전 충돌 409 |
| POST `/classrooms/{id}/questions/{qid}/resolve` | 담당 교수; expected_revision | answered 이외/버전 충돌 409 |
| PUT `/classrooms/{id}/assignments/{aid}/submission` | 학생 본인; 시연 텍스트 + expected_revision(최초 0) | 초안 404, closed/서버 마감 시각 이상/버전 충돌 409 |

`ClassroomStore.transaction(user_id,offering_id)`가 현재 수강/담당 교수 및 활성 상태를 같은 트랜잭션에서 확인해야 한다. 서비스도 반환 grant를 검사한다. 어댑터는 분반 범위·현재 권한·과제 상태/마감·질문/제출 revision·고유 제약·멱등 키와 payload를 잠금/CAS 트랜잭션으로 함께 다뤄야 한다. 테스트의 RLock fake는 이 인터페이스를 검증하는 예이며 MariaDB 동시성 검증이 아니다. 개인 제출 조회는 본인 ID로만 요청하고 교수 평가·타인 제출 조회는 이번 단계에 없다.

질문 원장의 author_id는 비공개 모델에만 있다. API용 `QuestionView`는 author_id 없이 is_mine만 반환한다. 학생은 본인 질문만, 담당 교수는 해당 분반 질문만 조회한다. 유효한 강의실 경로의 정상·검증·권한·미설치 오류 응답은 `Cache-Control: private, no-store`로 공유 캐시에 저장하지 않는다. 자료 URL은 시연 안전 기본값으로 인증·쿼리·fragment 없는 HTTPS 공개 참고 링크만 허용한다. 공식 학교 자료 URL 규칙을 확인한 것이 아니며 보호 첨부 URL/파일 다운로드를 구현한 것으로 표시하지 않는다.

시연용 처리 가정: 모든 분반 데이터 `source_kind=DEMO`, 질문은 교수에게만(작성자+담당 교수), 과제는 텍스트 2000자 이내, 마감 시각과 같은 요청부터 거부, 질문 open→answered→resolved. 이 가정은 실제 학교의 업무 규정이 아니며 공개 질문·답변 수정/철회·보존 기간·지각 제출·실제 평가 정책은 별도 결정 대상이다.

관련 FR/NFR/검사/미완료 범위는 [태스크 기록](../../../../../docs/dev-prep/TASK_CLASSROOMS_IMPLEMENTATION.md)을 따른다.
