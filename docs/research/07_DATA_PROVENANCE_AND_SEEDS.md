# 실제 공개 데이터와 시연 운영 데이터 설계

**설계 문서만 작성한다.** 아래는 DB 레코드 구성 계약이며 실제 학생·교수 계정, 성적, 출결, 상담, 지원서나 채팅을 수집하지 않았다. [PRD의 실제 연동 금지](../01_PRD.md), [기존 데이터 모델](../05_DATA_MODEL.md)을 준수한다.

## A. 공식 공개 데이터

| 데이터 | 원본 후보·확인 | 저장 단위 및 주의 |
|---|---|---|
| 학과/모집학과 | [학교 첫 화면](https://www.dit.ac.kr/kr/), [입학 학과](https://www.dit.ac.kr/ipsi/), [대학 메뉴](https://www.dit.ac.kr/kr/index.php?pCode=compusvr) | `department_source`, `valid_from/to`, `display_name`, `source_url`, `checked_at`. 페이지간 명칭 차이는 동일 코드로 임의 병합 금지. |
| 대학·학과 공개 공지 | [대학 공지](https://www.dit.ac.kr/kr/index.php?pCode=notice), [컴퓨터소프트웨어과](https://www.dit.ac.kr/cs/) | 원본 URL/게시일/작성 부서/첨부 존재/확인일 저장. 실제 본문·파일 재배포는 이용 권한/갱신 책임 검토 후. |
| 학사 일정 | [학사일정](https://www.dit.ac.kr/kr/index.php?pCode=univschedule) | 일정명·시작/종료·학년도·개정·확인일. 공개 페이지도 변경 가능하다고 고지. |
| 장학·근로·취업·프로그램 | [장학 게시판](https://www.dit.ac.kr/kr/index.php?pCode=scholarship), [취업센터](https://job.dit.ac.kr/page/main/), [프로그램 공고](https://www.dit.ac.kr/kr/index.php?idx=17786&mode=view&pCode=notice) | 주최/게시자/신청방식/원문/양식 URL을 공고별로 기록. 외부 제출 여부는 개인정보에서 분리. |
| 캠퍼스/시설 | [캠퍼스안내](https://www.dit.ac.kr/kr/index.php?pCode=compusvr), [생활관 시설](https://www.dit.ac.kr/kr/index.php?pCode=dormfacilities) | 건물/시설명·위치/안내 URL; 개별 강의실 좌표와 접근성 동선은 확인 전 공란. |
| 도서관 공개 서지 | [도서관](https://library.dit.ac.kr/Cheetah/DITL/Index/) | 서지/소장 메타가 공개되는 범위만. 대출자·예약자 등은 공개 데이터 아님. |
| 디지털 배지 안내 | [학교 발급 공지](https://www.dit.ac.kr/kr/index.php?idx=16265&mode=view&pCode=notice) | 발급 절차·기준 첨부 존재는 공식 공개 정보. 개인별 발급 이력/이메일/지갑은 공개 데이터 아님. |

공식 페이지의 숫자와 기한을 시연 DB에 옮길 때 `source_kind=official_public`, `source_url`, `source_published_at`, `checked_at=2026-10-29`, `valid_for_term`, `fetched_or_entered_by`, `review_status`를 요구한다. 자동 수집 권한/빈도는 미정이며 이번 작업은 공개 페이지 확인만 했다. 원문 수정 시 기존 스냅샷을 덮지 않고 개정 레코드를 만든다.

## B. 가상 시연 운영 데이터

`source_kind=synthetic_demo`, `is_official_record=false`, `demo_scenario_id`를 모든 개인·업무 레코드에 넣고 화면에 **시연용 가상 데이터**로 표시한다. 실존 학생 이름/학번/연락처/생년월일을 사용하지 않는다. 가상 교수/조교도 실존 교직원 이름을 사용하지 않는다. 아이디/메일은 예시 전용 도메인과 불가능한 학번 패턴을 사용한다.

| 레코드 묶음 | 최소 연관 관계 | 시연 검증 |
|---|---|---|
| 조직·학기 | `departments` 2개, `academic_terms` 1개, `class_cohorts` 각 학년 | 학과 A/B 격리와 학년별 채널 검증. 공식 학과명 사용 시 실제 학생/교수 연결 금지. |
| 계정·역할 | 가상 학생 A1/A2/B1, 교수 A, 조교 A, 교무 담당, 사서, 상담자, 관리자; `role_assignments`에 범위 | A1이 B 학과 자료를 못 보고 조교가 학교 전체 권한을 얻지 못함. |
| 강의·수강 | 학기→`course_offerings` 2개→시간표→`enrollments` A1/A2; 교수 A 배정 | 시간표·내 강의실·자료·과제·출결이 같은 분반 FK 사용. |
| 공지·채팅 | 조교 A 공지 1건→학과/학년 대상→`notice_outbox`→`notice_deliveries`→공식 카드/알림 | 공지 수정 뒤 카드 원본 최신판; A/B 격리; 중복 이벤트 1건. |
| LMS·출결 | 분반→가상 자료/과제/제출/온라인 학습 이벤트/대면 출결 세션/기록 | 온라인 학습 진도와 대면 체크를 별도 원장으로 보여 줌; 공식 출석 판정 아님. |
| 기회·모집 | 공식 공개 공고 **링크 메타** 또는 시연 공고→학생 A1 개인 체크리스트→실명 모집→B1 지원/승인 | 외부 장학은 `self_reported`만; 공모전 모집은 공고 ID 참조; 정원 경합. |
| 커뮤니티 | A1 익명 글·A2 댓글, B1 실명 프로필·모집 | 공개 익명 응답에서 내부 사용자 FK 제거. |
| 도서관·생활관·입학 | 가상 서지/소장본/대출/예약, 가상 생활관 신청, 가상 입학 지원서 | 같은 시연 ID와 상태 전이. 실제 대출·입학·납부 결과처럼 표시 금지. |
| 디지털 배지 | 가상 교과/비교과 이수→가상 발급 주체→가상 배지 메타/지갑 | 공식 인증 배지와 혼동되지 않도록 시연 워터마크·검증 URL 없음. |
| 민원·상담 | 가상 민원 1건과 **민감 내용 없는** 상담 접근 테스트 레코드 | 일반 검색/AI/알림 본문에 노출되지 않음. |

## 관계·상태 설계 보완

- 공통 `source_registry(source_id, source_kind, canonical_url, published_at, checked_at, review_status, license_note)`와 각 공개 콘텐츠의 `source_id`를 제안한다. 실제 도입 여부는 설계 승인 필요.
- 입학: `admission_cycles → admission_tracks → applications → required_documents / interviews / decisions / billing_events`. 지원자 계정은 `profiles`의 학생 신분으로 자동 승격하지 않는다.
- 학사: `program_versions → curriculum_requirements`, `course_catalog → course_offerings → enrollments`, `student_academic_status_events`, `grade_entries / grade_change_requests`, `tuition_invoices / payment_confirmations`. 신청과 확정 원장을 분리한다.
- LMS/출결: `learning_content → attempts/progress_events`, `assessments → exam_attempts`, `attendance_sessions → attendance_records`. 온라인 출석 근거와 대면 캠퍼스락 방식은 출처 필드와 판정자를 분리한다.
- 도서관: `bibliographic_records → holdings → item_copies → loans / holds`; 공간은 `facilities → reservation_slots → reservations`. 같은 소장본·슬롯 동시 배정 방지.
- 생활관: `residence_terms → applications → assignments / cancellations`. 실제 호실/학생 배정 데이터는 사용하지 않는다.
- 지원: `service_requests → assignments → responses`, 민감 고충은 별도 접근 영역; `career_profiles / resumes / counseling_appointments`도 본인/상담 담당 범위로 제한한다.

## 시연 데이터 일관성 점검

1. 모든 가상 학생의 학과·학년·수강·채널·공지 대상이 하나의 조직/학기 원장을 참조한다.
2. 개인 시간표는 `timetable_slots`와 `enrollments`에서 계산한다. 스크린샷용 문자열을 별도 사실처럼 저장하지 않는다.
3. 성적·출결·증명·합격·납부는 “시연” 상태 필드를 함께 반환한다. 공식 효력으로 표시하지 않는다.
4. 공고 원문이 실제 공개 자료인 경우 `official_public` 메타와 학생의 가상 준비 기록을 분리한다. 첨부 원본 저작권/재배포 조건 미확인 시 링크만 보유한다.
5. 데이터 삭제·재생성은 `demo_scenario_id` 범위 안에서만 정의하며 공식 공개 스냅샷과 섞지 않는다.
