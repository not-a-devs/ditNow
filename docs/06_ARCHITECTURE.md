# 기술 아키텍처 및 통합 계약

> 프런트 React/TypeScript/Vite/Tailwind CSS와 백엔드 FastAPI는 [DEC-015](11_DECISION_LOG.md) **[확정]**이다. MariaDB는 DEC-016으로 확정했다. DB 운영·인증·파일·실시간·호스팅 공급자, 지역과 비용은 [OPEN-002](11_DECISION_LOG.md) **[미결정]**이다. 현재 `services/api/`에는 공개 health·공통 오류·설정·로그·테스트만 구현했고, 아래 업무 API와 DB는 아직 설계다.

## 1. 확정 스택과 공급자 후보
| 계층 | 상태·기술 | 이유/제약 |
|---|---|---|
| 프런트·UI | **확정:** React + TypeScript + Vite + Tailwind CSS | `apps/web/`에 새로 작성; 사전 `mvp/` 코드 복사 금지 |
| 백엔드 | **확정:** FastAPI | 모든 보호 API의 인증 검증·범위 권한·입력 검증·응답 필터 담당 |
| DB | **확정:** MariaDB + 최소 GRANT + FastAPI 범위 검사 | 제품 선택은 DEC-016; 접속/호스팅/권한은 OPEN-002; FK·unique·트랜잭션 요구는 유지 |
| 인증 | **미결정:** 공급자·세션/토큰 발급 방식 | FastAPI가 토큰/세션을 검증하고 현재 역할·소속을 권위 원장에서 재조회 |
| 파일 | **미결정:** 비공개 저장소 + 권한 있는 단기 접근 URL | 공급자 결정 전 실제 파일 연동 금지 |
| 실시간 채팅 | **미결정:** FastAPI WebSocket 또는 별도 공급자 + 영속 원장 | 구독 단계에서도 현재 소속 권한 재검증; 메모리에만 저장 금지 |
| 스트리밍 | **미결정 후보:** LiveKit 기반 SFU 등 검증된 WebRTC 솔루션 | 교수 1→학생 다수, 화면 공유; PoC·비용 승인 전 선택하지 않음 |
| AI | 서버 측 AI API + JSON 스키마 검증 + 사용량 기록 | 브라우저 키 노출 방지 |
| 배포 | **미결정:** 웹/API/DB 호스팅과 지역·비용 | 계정·예산 승인 전 배포하지 않음 |
| 품질 | 현재 TypeScript 타입/빌드; 향후 API·권한·E2E 테스트 | 아직 없는 lint/test 명령을 실행 완료로 기록하지 않음 |

## 2. 계층 구조
```text
Browser (React/Vite/Tailwind SPA)
  ├─ Session UI + Route Guards + Responsive UI
  ├─ Features: notices / department / community / opportunity / classroom / home
  ├─ OpenAPI 기반 Typed API Client (서버 검증이 권위)
  └─ Realtime Subscriber (channel + class)
            │  HTTPS / 승인된 세션 또는 토큰
            ▼
FastAPI: 인증 검증 → 현재 역할·소속 조회 → 자원 권한 → Pydantic 검증
   ├─ 업무 API/트랜잭션/outbox 소비자 (공식 공지 → 카드·알림)
   ├─ MariaDB: 전용 최소 GRANT + FK/unique/트랜잭션; 모든 보호 조회에 서버 범위 조건
   ├─ 공급자 미정 비공개 저장소·실시간·미디어
   └─ 서버 비밀값으로 호출하는 AI API
```

## 3. 현재 및 제안 프로젝트 디렉터리
```text
mvp/                         # 사전 프로토타입 보존; 최종 시연/제출/소스 재사용 제외
apps/web/                    # 신규 프런트 구현 브랜치; main에는 아직 없음
chatbot/                     # 통합 RAG 재사용 대상, 별도 최종 사용자 시스템 아님
services/api/                # 실제 FastAPI 기반; 업무 서비스는 단계적 구현
infra/db/migrations/         # 제안: MariaDB 초기 스키마/버전 관리 작업 중; 적용은 별도 게이트
packages/contracts/          # 제안: OpenAPI/타입 생성 결과물
tests/{unit,integration,e2e}/
docs/   # 이 명세 패키지
```

## 4. 계약 설계 원칙
- FastAPI의 Pydantic 입출력 모델과 OpenAPI를 서버 계약 원본으로 삼고 프런트 타입을 생성·검증한다. 서버 입력·출력 검증은 필수다.
- API 성공: 자원 ID와 현재 상태/버전. 실패: `{code, message, field_errors?, retryable?}`로 통일; 내부 스택트레이스 노출 금지.
- 보호된 자원에 대한 클라이언트 URL 조작만으로 소유권 우회 불가능.
- 선택된 인증 방식에 따라 FastAPI가 JWT 서명·만료·발급자·대상 또는 불투명 세션 조회·만료·폐기를 검증한다. 검증된 공급자 주체를 내부 사용자 ID로 매핑하고, 클라이언트의 role/scope는 신뢰하지 않는다.
- 브라우저는 보호 데이터에 직접 DB 연결하지 않고 FastAPI만 호출한다. FastAPI가 각 요청의 역할·소속·소유권·상태를 검사한다. MariaDB 최소 GRANT·스코프 질의·제약은 추가 방어선이며 서버 검사 생략 근거가 아니다. PostgreSQL 네이티브 RLS가 있는 것으로 가정하지 않는다.
- 목록 조회에는 `limit/after` 기준 페이지네이션과 관계 집계의 N+1 방지.
- 이벤트의 소스, 전송 성공, 최종 UI 도달은 서로 다른 사실로 로그에 남김.

## 5. 공식 공지 자동 배포 상세 시퀀스
1. 승인된 조교/교수 → FastAPI `publishNotice` 업무 API 호출(권한 + 입력 검증 + 멱등성키).
2. DB 트랜잭션에 `notices` upsert / `notice_outbox` insert.
3. outbox consumer가 대상 채널 조회(학과·학년·수업); `notice_deliveries` unique insert.
4. 채널 `system_notice_card` 메시지 생성(원본 참조). `notifications`의 recipient+dedupe 작성.
5. 실시간 이벤트/재조회로 사용자 목록 반영; 실패 시 안전한 재처리.
6. 원본 정정: `revision` 증가, 카드 상세는 최신판 참조; 알림은 중요 수정 때만.

## 6. 익명 공개 API 분리
- `anonymous_posts_private`와 익명 작성자 연결 정보는 FastAPI의 제한된 업무 경로에서만 조회.
- 일반 사용자에게는 익명 post public view/projection으로 제목·내용·ID만 제공.
- 작성자 수정/삭제는 서버에서 인증 UID와 private owner를 직접 확인.
- 브라우저에 DB 테이블 직접 SELECT 권한을 열어두고 UI에서 author_id만 숨기는 방식은 금지.

## 7. 실시간 수업 미디어 기술 검증 (P1 별도 PoC)
- 교수 브라우저에서 사용자 동작 `getDisplayMedia()` → 화면 공유 선택 → LiveKit publish.
- 서버가 수업 담당자만 `publish` 권한의 짧은 토큰, 등록 수강생만 `subscribe` 토큰 발행.
- 기본 오디오 송출/녹화는 비활성. 학생 모바일 앱/브라우저에서 `playsInline`, 확대 UI, 기기별 제약 안내.
- **PoC 통과 조건**: 교수 1 + 수강생 2, 서로 다른 계정/브라우저, 화면 공유 성공·종료·권한거부·미수강생 차단 확인.
- 라이브 영상은 학생 각자 원본 PPT/PDF 파일을 독립적으로 확대하는 기능과 분리.
- 실시간 화면 공유가 제출 시점까지 미검증이면 기능을 `beta/준비 중`으로 표시하거나 시연 경로에서 제외.

## 8. AI 개인화 브리핑
- 서비스 쿼리 → 서버에서 권한 필터 → 일정/마감 계산 → 최소 데이터(식별자·제목·날짜·출처)로 모델 호출 → 정형 JSON 유효성 검증 → 학생에게 카드 표시.
- 원본 공지/학생 게시글은 모델에 대한 **데이터**이며 명령이 아님. 모델이 제공한 `source_id`는 DB 권한+존재 재검증.
- 실패 시 원본 카드와 규칙 기반 '오늘 확인할 일'을 제공하고 AI 미사용 상태를 명확히 표시.

## 9. 시스템 설계 의사결정 시점
- DEC-015의 프런트/FastAPI 선택을 유지하고 DEC-016의 MariaDB를 적용하고 OPEN-002의 DB 운영·인증·호스팅·비용을 별도 결정한다.
- 스트리밍은 PoC로 비용·권한·지원 브라우저 확인 후 사용 결정.
- 학과 채팅/알림 실시간은 서버 구독 권한과 메시지 검색 범위까지 포함해 QA.

## 10. 통합 RAG와 공통 원장
DEC-017에 따라 chatbot/ 구현을 services/api/의 제한된 adapter로 재사용한다. 기존 standalone 로그인·세션·개인 학적 DB를 공통 API에 그대로 mount하지 않는다. 검증된 공통 신원→현재 소속/역할→허용 원본 조회→최소 문맥 전달 순서를 적용한다. LLM이 DB 접근 권한을 결정하지 않는다. 통합 인증이 없으면 개인 정보 기능은 닫고 공개 시설 조회부터 테스트한다.

DEC-018의 전체 92개 1차 구현은 [진행표](dev-prep/06_FEATURE_IMPLEMENTATION_STATUS.csv)로 관리한다. FE/BE/DB가 준비된 기능도 실제 통합·회귀 검사와 사용자 직접 검수 전 전체 VERIFIED로 올리지 않는다.

## 11. 확정 DB 운영 경계 (DEC-019)
DB는 별도 신규 클라우드 개설 대신 팀원 Proxmox VM MariaDB11.4/Tailscale3307을 사용한다. 앱 ditnow_app은 ditnow DML만, ditnow_migrator는 승인된 migration 전용, chatbot 계정은 ditnow_chatbot 자료에 한정한다. 실제 GRANT는 미검증이다. [운영 검사](dev-prep/07_DB_CONNECTIVITY_AND_ROLES.md)의 TCP/자격/TLS/스키마 선행 조건 전 실제 연결·변경을 실행하지 않는다. 기존 chatbot auto create_all/seed는 운영 경로에서 제거하는 별도 보안 PR로 관리한다.
