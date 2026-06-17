from pathlib import Path

from ai_bot.analyzer.result import AnalysisResult


class FakeAnalyzer:
    """Plan 2 단계의 stub. Plan 3에서 real Claude Agent SDK 기반으로 교체된다."""

    async def analyze(
        self,
        *,
        worktree_path: Path,
        error_class: str,
        commit_sha: str,
        log_lines: list,
    ) -> AnalysisResult:
        return AnalysisResult(
            category="CODE_BUG",
            confidence=0.85,
            root_cause=f"[FAKE] {error_class} in {worktree_path.name} (commit {commit_sha[:8]})",
            patch=None,
            model="fake",
            tool_calls_count=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=100,
        )
