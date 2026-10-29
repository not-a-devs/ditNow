# Library 1차 모듈

TASK-H-LIBRARY의 공급자 독립 도서·공간 시연 모듈이다. 기본 앱에 라우터를 연결하지 않는다. 승인된 공통 인증/현재 자격/가상 정책/트랜잭션 저장소가 없으면 기본 의존성은 503을 반환한다. 실행용 메모리 저장소·운영 계정·실제 도서관 API·DB는 만들지 않는다.

통합 담당자가 라우터를 `/api/v1` 아래 등록하면 다음 경로를 사용할 수 있다. 현재 공개 OpenAPI에는 미등록 경로를 추가하지 않는다.

| 경로 | 입력 / 출력 | 범위 |
| --- | --- | --- |
| GET `/library/catalog` | q≤120, offset 0~10000, limit 1~50 → items/offset/has_more | 승인된 가상 공개 서지 검색 |
| GET `/library/slots` | 가상 공간의 공개 시간대·가용 표시, 최대100 | 개인 예약자 식별자 없음 |
| GET `/library/me` | 본인 대출·희망도서·공간 예약·주입된 가상 정책 | 현재 활성 신원만, 타인 필터 |
| POST `/library/me/loans/{id}/renew` | expected_revision → 연장 결과 | 본인/현재 자격/주입 정책/CAS |
| POST `/library/me/wishes` | title≤200, author≤100, reason≤500 → requested | 본인 희망도서 시연 요청 |
| POST `/library/me/slots/{id}/reserve` | expected_revision → reserved | 현재 자격/미시작 시간대/범위 중복/상한 |
| POST `/library/me/bookings/{id}/cancel` | expected_revision → cancelled | 본인/현재 자격/미시작 예약/CAS |

모든 쓰기는 `Idempotency-Key` 16~100자 영숫자/하이픈을 요구한다. actor+operation+resource namespace와 정규화 payload 해시를 원자 저장해야 한다. 같은 키·다른 payload는409, 재시도는 현재 자격을 다시 확인하고 본인 결과만 반환한다. 연장 재시도는 CAS·횟수 제한 재적용으로 중복 연장되지 않아야 한다. 전제는 실제 어댑터가 replay/상태/권한을 같은 트랜잭션에서 보장하는 것이다.

`LibraryPolicy`는 이름과 DEMO 출처·연장일수·연장횟수·연체 허용·기준시각·활성 예약 상한을 명시적으로 주입한다. 실행 기본값은 없다. 테스트의 7일/1회/1건은 학교 규정이 아니다. 연장은 현재 기한을 줄이지 않으며 서버 aware UTC 시각으로 판정한다. 예약은 시작 시각과 같거나 지난 경우 시연 변경을 거부한다. 실제 도서 대출 기간·자격·연체·예약 취소 정책은 운영 전 별도 승인한다.

저장소는 현재 신원/자격·소유권·revision을 검증하고 대출 소장본·공간 시간 범위를 잠근다. 다른 slot ID라도 같은 물리 공간의 `[starts_at,ends_at)` 범위가 겹치면 중복 예약을 막아야 한다. `library_items`의 활성 대출 유일성도 실제 대출 기능 추가 전 보장해야 한다. 테스트 fake의 RLock은 실제 MariaDB 격리·영속성 검증이 아니다.

개인 응답에서 owner_id를 제외하며 기본 라우트의 정상·입력·권한·미설치·예상외 오류 응답에 `Cache-Control: private, no-store`를 설정한다. 내부 예외와 원문 요청은 로그·사용자 메시지에 출력하지 않는다. 외부 원문은 시연 안전 기본값으로 사용자 정보·query·fragment 없는 HTTPS만 허용하며 서버가 외부 URL을 가져오지는 않는다.

상태·검증·미구현 범위는 [태스크 기록](../../../../../docs/dev-prep/TASK_LIBRARY_IMPLEMENTATION.md)을 참고한다.
