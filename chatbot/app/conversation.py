"""후속 질문을 대화 기록 없이도 통하는 질문으로 바꾼다."""

import logging

from .llm import ChatMessage, LLMClient, LLMError
from .prompt import CONDENSE_PROMPT
from .schemas import Turn

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 200
# 답은 한 줄이지만 최신 모델은 답 전에 추론 토큰을 쓴다 (의도 분류와 같은 이유)
CONDENSE_MAX_TOKENS = 1024


async def condense(history: list[Turn], question: str, llm: LLMClient) -> str:
    """'거기 몇 시까지 해?' → '정보관 편의점 몇 시까지 해?'. 실패하면 원래 질문."""
    transcript = "\n".join(
        f"{'학생' if t.role == 'user' else '도우미'}: {t.content}" for t in history
    )
    messages = [
        ChatMessage(role="system", content=CONDENSE_PROMPT),
        ChatMessage(
            role="user", content=f"<history>\n{transcript}\n</history>\n\n마지막 질문: {question}"
        ),
    ]
    try:
        raw = await llm.chat(messages, temperature=0, max_tokens=CONDENSE_MAX_TOKENS)
    except LLMError as e:
        logger.warning("후속 질문 재작성 실패: %s", type(e).__name__)
        return question
    lines = [line.strip().strip("\"'") for line in raw.strip().splitlines() if line.strip()]
    return lines[0][:MAX_QUESTION_CHARS] if lines else question
