# 기술 아키텍처 및 통합 계약

> 현재 기술 스택은 **[설계 기본값]**. 팀 승인 전에는 유일한 가능한 구현 방식이라고 주장하지 않는다. 우선 **하나의 일관된 스택**을 기준으로 AI가 작업하도록 하기 위함이다.

## 1. 권장 기본 스택
| 계층 | 제안 | 이유/제약 |
|---|---|---|
| 프런트 | React + TypeScript + Vite | 빠른 MVP, 팀 경험·반응형 웹 |
| UI | Tailwind CSS 또는 공통 CSS 토큰 + 재사용 컴포넌트 (둘 중 하나만 승인) | 일관성, 스타일 중복 방지 |
| 서버/Auth/DB | Supabase Auth + PostgreSQL + RLS + Edge Functions | 인증·실시간 DB·파일·권한 구성 |
| 파일 | Supabase Storage private bucket + 서명된 읽기 URL | 수업/장학금 양식 안전한 배포 |
| 실시간 채팅 | Postgres 영속 + Supabase Realtime 구독 | 메모리에만 메시지 저장 금지 |
| 스트리밍 | LiveKit 기반 SFU 등 검증된 WebRTC 솔루션 | 교수 1→학생 다수, 화면 공유 |
| AI | 서버 측 AI API + JSON 스키마 검증 + 사용량 기록 | 브라우저 키 노출 방지 |
| 배포 | Vercel + Supabase 가까운 지역 선택 | 제출 URL, 성능 측정 |
| 품질 | TypeScript strict, ESLint, Vitest, Playwright, Lighthouse | 근거 가능한 완료 판정 |

## 2. 계층 구조
```text
Browser (React SPA)
  ├─ Auth Session + Route Guards + Responsive UI
  ├─ Features: notices / department / community / opportunity / classroom / home
  ├─ Typed API Client (server validation is authoritative)
  └─ Realtime Subscriber (channel + class)
            │  auth JWT / HTTPS
            ▼
Supabase Auth ─── Edge Functions (official actions, AI, token issuance)
            │                    │
            ├─ PostgreSQL + RLS  ├─ AI provider API (server key)
            ├─ Private Storage   └─ LiveKit room/token service (optional)
            └─ Outbox Dispatcher (official notice → deliveries + notifications)
```

## 3. 권장 프로젝트 디렉터리 (코드 작성 후)
```text
src/
  app/{router,providers}/
  features/{auth,home,notices,department,community,opportunity,classroom,ai}/
  shared/{ui,lib,types,validation}/
supabase/
  migrations/
  functions/{publish-notice,issue-live-token,generate-briefing}/
tests/{unit,integration,e2e}/
docs/   # 이 명세 패키지
```

## 4. 계약 설계 원칙
- 클라이언트와 서버에 공통 Zod/JSON schema를 정의하고 server-side validation 필수.
- API 성공: 자원 ID와 현재 상태/버전. 실패: `{code, message, field_errors?, retryable?}`로 통일; 내부 스택트레이스 노출 금지.
- 보호된 자원에 대한 클라이언트 URL 조작만으로 소유권 우회 불가능.
- 로그인 토큰은 인증 SDK 규칙으로 다루고 서버는 유효성 확인 후 UID·role scope 계산.
- 데이터 직접 CRUD는 RLS로 보호된 Supabase 클라이언트 경로 사용 가능; 역할 승격·공지 발행·동시 승인·AI·미디어 토큰은 서버 함수 사용.
- 목록 조회에는 `limit/after` 기준 페이지네이션과 관계 집계의 N+1 방지.
- 이벤트의 소스, 전송 성공, 최종 UI 도달은 서로 다른 사실로 로그에 남김.

## 5. 공식 공지 자동 배포 상세 시퀀스
1. 승인된 조교/교수 → `publishNotice` 함수 호출(권한 + 입력 검증 + 멱등성키).
2. DB 트랜잭션에 `notices` upsert / `notice_outbox` insert.
3. outbox consumer가 대상 채널 조회(학과·학년·수업); `notice_deliveries` unique insert.
4. 채널 `system_notice_card` 메시지 생성(원본 참조). `notifications`의 recipient+dedupe 작성.
5. 실시간 이벤트/재조회로 사용자 목록 반영; 실패 시 안전한 재처리.
6. 원본 정정: `revision` 증가, 카드 상세는 최신판 참조; 알림은 중요 수정 때만.

## 6. 익명 공개 API 분리
- `anonymous_posts_private`와 익명 작성자 연결 정보는 신뢰된 서버에서만 조회.
- 일반 사용자에게는 익명 post public view/projection으로 제목·내용·ID만 제공.
- 작성자 수정/삭제는 서버에서 인증 UID와 private owner를 직접 확인.
- 공개 Postgres 테이블 직접 SELECT 권한을 열어두고 UI에서 author_id만 숨기는 방식은 금지.

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
- 공개 저장소 생성 여부·배포 설정 확인 후 스택 확정.
- 스트리밍은 PoC로 비용·권한·지원 브라우저 확인 후 사용 결정.
- 학과 채팅/알림 실시간은 서버 구독 권한과 메시지 검색 범위까지 포함해 QA.
