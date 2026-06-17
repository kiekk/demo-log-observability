from typing import Literal

from pydantic import BaseModel, Field


class Patch(BaseModel):
    file_path: str
    old_content: str
    new_content: str


class AnalysisResult(BaseModel):
    category: Literal["CODE_BUG", "DATA_ANOMALY", "INFRA_ISSUE", "INSUFFICIENT_CONTEXT", "BENIGN_ERROR"]
    confidence: float = Field(ge=0.0, le=1.0)
    root_cause: str

    # CODE_BUG / BENIGN_ERROR
    patch: Patch | None = None

    # DATA_ANOMALY
    data_hypothesis: str | None = None
    verification_sql: list[str] = Field(default_factory=list)
    verification_logql: list[str] = Field(default_factory=list)

    # INFRA_ISSUE
    infra_checklist: list[str] = Field(default_factory=list)
    related_metrics: list[str] = Field(default_factory=list)

    # BENIGN_ERROR
    alert_rule_proposal: str | None = None

    # 메타데이터
    tool_calls_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    model: str = "fake"
