"""Synthetic exceptions only: prove logging boundaries without SDK calls or actual secrets."""

import asyncio
import logging

import pytest

from app.conversation import condense
from app.intents import classify_with_llm
from app.llm import LLMClient, LLMError
from app.schemas import Turn

SENTINEL = "SYNTHETIC_PRIVATE_QUESTION_AND_CREDENTIAL_NOT_A_REAL_SECRET"


class SyntheticLLM(LLMClient):
    def __init__(self, *, malformed_json=False):
        self.malformed_json = malformed_json

    async def chat(self, messages, **kwargs):
        if self.malformed_json:
            return "{" + SENTINEL + "}"
        raise LLMError(SENTINEL)


@pytest.mark.parametrize("operation", ["classify", "condense", "malformed_json"])
def test_llm_fallback_logs_only_error_type_not_exception_payload(caplog, operation):
    llm = SyntheticLLM(malformed_json=operation == "malformed_json")
    with caplog.at_level(logging.WARNING):
        result = (
            asyncio.run(condense([Turn(role="user", content=SENTINEL)], "fictional-question", llm))
            if operation == "condense"
            else asyncio.run(classify_with_llm(SENTINEL, llm))
        )
    assert result == ("fictional-question" if operation == "condense" else None)
    assert len(caplog.records) == 1
    expected_type = "JSONDecodeError" if operation == "malformed_json" else "LLMError"
    assert expected_type in caplog.records[0].getMessage()
    assert caplog.records[0].args == (expected_type,)
    assert caplog.records[0].exc_info is None
    assert SENTINEL not in caplog.text
