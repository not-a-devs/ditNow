# SKILL: 외부 LLM 클라이언트

> 대상 파일: `app/llm/*.py`, `app/config.py`

## 1. 인터페이스

파이프라인은 **공급자를 몰라야** 합니다. 모든 클라이언트는 아래 인터페이스를 구현합니다.

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel

class ChatMessage(BaseModel):
    role: str   # "system" | "user" | "assistant"
    content: str

class LLMClient(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> str:
        """메시지 목록을 보내고 답변 텍스트를 반환한다."""
```

## 2. 공급자 선택 (`.env`)

```env
LLM_PROVIDER=openai            # openai | anthropic | openai_compatible | fake
LLM_MODEL=                     # 사용할 모델 이름
LLM_API_KEY=
LLM_BASE_URL=                  # openai_compatible일 때만 (예: 로컬 vLLM, Ollama 등)
LLM_TIMEOUT_SEC=20
```

- `app/llm/__init__.py`에 `get_llm_client(settings) -> LLMClient` 팩토리를 둡니다.
- `openai_compatible`은 OpenAI SDK에 `base_url`만 바꿔 재사용합니다. 나중에 팀이 파인튜닝한 한국어 모델을 서빙하면 이 경로로 붙입니다.
- 모델 이름은 코드에 하드코딩하지 않고 `.env`에서만 읽습니다.

## 3. 공급자별 구현 메모

| 공급자 | SDK | 주의점 |
|---|---|---|
| OpenAI / 호환 서버 | `openai` (AsyncOpenAI) | system 메시지를 `messages`에 그대로 포함 |
| Anthropic | `anthropic` (AsyncAnthropic) | system 메시지는 `messages`에서 빼서 `system=` 파라미터로 전달. 최신 Claude 모델은 `temperature`를 받지 않아(400) **보내지 않음**. `stop_reason == "refusal"`이면 `LLMError` |

## 4. 오류 처리

- 타임아웃·네트워크·429·5xx 오류는 **최대 2회 재시도** — 두 SDK의 내장 재시도(`max_retries=2`, 지수 백오프)를 쓰고 직접 구현하지 않습니다.
- 그 밖의 SDK 오류는 `LLMError`로 감싸서 올립니다.
- 401/403(키 오류)은 재시도하지 않고 즉시 `LLMAuthError`를 발생시킵니다.
- 최종 실패 시 API는 사용자에게 `"지금은 답변을 만들 수 없어요. 잠시 후 다시 시도해 주세요."`를 반환하고, 서버 로그에 원인을 남깁니다.
- **로그에 API 키나 전체 프롬프트를 남기지 않습니다.** (요청 id, 모델명, 소요 시간, 토큰 수만)

## 5. 테스트용 가짜 클라이언트

`app/llm/fake_client.py`에 `FakeLLMClient`를 둡니다.
- 받은 컨텍스트 문서 id 목록을 그대로 답변에 넣어 돌려줍니다.
- `pytest`에서는 항상 이 클라이언트를 쓰고, **테스트가 실제 API를 호출하지 않게** 합니다.

## 6. 공급자 추가 체크리스트

- [ ] `LLMClient` 상속, `chat()` 구현
- [ ] 팩토리에 분기 추가
- [ ] `.env.example`에 필요한 키 추가
- [ ] `requirements.txt`에 SDK 추가
