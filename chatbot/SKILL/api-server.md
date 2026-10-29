# SKILL: API 서버 (FastAPI)

> 대상 파일: `app/main.py`, `app/schemas.py`(API 모델), `app/config.py`

## 1. 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/health` | 서버·데이터 로드 상태 확인 |
| `POST` | `/ask` | 질문 → 답변 (핵심). 개인 질문은 `Authorization: Bearer <token>` 필요 |
| `POST` | `/auth/login` | 학번·초기 비밀번호 로그인 → 토큰 (`SKILL/student-assistant.md`) |
| `POST` | `/auth/logout` | 토큰 폐기 |
| `GET` | `/facilities` | 시설 목록 (프론트 지도 표시용) |
| `GET` | `/facilities/{id}` | 시설 상세 |
| `GET` | `/admin/questions` | 질문 로그 (`X-Admin-Token`). 기본은 답을 못 찾은 질문만, `only_failed=false`면 전체 |
| `POST` | `/admin/reload` | JSON 데이터 다시 읽기 (`X-Admin-Token` 헤더 = `.env`의 `ADMIN_TOKEN`, 비어 있으면 비활성) |

## 2. `/ask` 요청·응답

```jsonc
// 요청
{ "question": "컴소과 어디 있어?", "user_location": { "lat": 35.16, "lng": 129.07 } }  // user_location은 선택

// 응답
{
  "answer": "컴퓨터소프트웨어과 학과사무실은 미래관에 있어요.",
  "sources": ["dept_cs"],
  "locations": [
    { "id": "dept_cs", "name": "컴퓨터소프트웨어과", "building": "미래관", "lat": 35.1662, "lng": 129.0723 }
  ],
  "found": true,
  "latency_ms": 840
}
```

- `intent`: `campus` | `next_class` | `day_classes` | `my_courses` | `grades` | `exams` | `remaining_credits`
- `classified_by`: 의도를 고른 방법 (`keyword` | `llm`)
- `rewritten_question`: `history`로 후속 질문을 바꿨을 때 실제로 처리한 질문
- `need_login=true`면 개인 질문인데 로그인하지 않은 것입니다. 프론트는 로그인 화면으로 안내합니다.
- 잘못되거나 만료된 토큰을 보내면 `401`입니다. 토큰 없이 보내면 교내 질문은 정상 응답합니다.
- `found=false`이면 데이터에 없다는 뜻입니다. 프론트는 "관리자에게 제보하기" 같은 UI를 띄울 수 있습니다.
- `user_location`은 지금은 응답에 그대로 쓰지 않고, 이후 길찾기 기능에서 사용합니다. **로그에 저장하지 않습니다.**

## 3. 구조 규칙

- 앱 시작 시 `lifespan`에서 데이터 로드 → Retriever 생성 → LLMClient 생성, `app.state`에 보관합니다.
- 엔드포인트 함수는 얇게 유지하고, 로직은 `rag.py`의 `answer_question()`에 둡니다.
- 모든 요청·응답은 Pydantic 모델로 정의합니다.
- `question`은 1~200자 제한, 빈 문자열·특수문자만 있는 질문은 422.
- 앱은 `create_app(settings)`로 만들고, 테스트에서는 `LLM_PROVIDER=fake` 설정을 주입합니다.

## 4. React 연동

- CORS 허용 출처는 `.env`의 `CORS_ORIGINS`(쉼표 구분)에서 읽습니다.
  - 개발 기본값: `http://localhost:5173,http://localhost:3000`
- 프론트 호출 예시 (후속 질문을 위해 직전 대화를 `history`로 함께 보냄):
  ```js
  // messages: [{ role: "user" | "assistant", content: string }, ...] 화면에 쌓인 대화
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token && { Authorization: `Bearer ${token}` }),
    },
    body: JSON.stringify({ question, history: messages.slice(-6) }),
  });
  const data = await res.json(); // data.need_login이면 로그인 화면으로
  ```
- `history`: 직전 대화 **최대 6턴**(오래된 것부터), 턴당 1000자. 서버는 대화를 저장하지 않습니다.
  - 보내면 서버가 "거기 몇 시까지 해?"를 "정보관 편의점 몇 시까지 해?"처럼 바꿔 처리하고,
    응답 `rewritten_question`에 바꾼 질문을 담습니다(바뀌지 않았으면 `null`).
  - 질문 재작성에 LLM 호출이 1번 더 들어 응답이 약간 느려집니다. 첫 질문은 `history` 없이 보내세요.

## 5. 운영 고려

- 간단한 IP당 요청 제한(분당 20회)을 미들웨어로 둡니다 — 해커톤 시연 중 LLM 비용 폭주 방지.
- 응답 시간 목표: 평균 2초 이내. 같은 질문(정규화 기준)은 메모리 캐시(TTL 10분)로 재사용합니다.
  - 캐시 응답은 요청 제한에 세지 않고, LLM 실패 응답은 캐시하지 않습니다.
- 요청 제한·캐시는 프로세스 메모리에 있으므로 **워커 1개(단일 프로세스)** 를 전제로 합니다.
