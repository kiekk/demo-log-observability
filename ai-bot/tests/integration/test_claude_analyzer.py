import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REAL_LLM") != "1",
    reason="실제 Claude API 호출 — RUN_REAL_LLM=1로 enable",
)


@pytest.mark.asyncio
async def test_analyzer_instantiates() -> None:
    from ai_bot.analyzer.claude import ClaudeAnalyzer

    analyzer = ClaudeAnalyzer()
    assert analyzer._model
    assert analyzer._max_turns > 0
    assert analyzer._timeout > 0
