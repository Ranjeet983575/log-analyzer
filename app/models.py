from pydantic import BaseModel, Field
from enum import Enum


class SeverityLevel(str, Enum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    UNKNOWN = "unknown"


class LogAnalysisRequest(BaseModel):
    logs: str = Field(
        ...,
        min_length=1,
        description="Raw system log text to analyze",
        json_schema_extra={
            "example": (
                "2026-03-21 08:12:01 ERROR [nginx] upstream timed out "
                "(110: Connection timed out) while connecting to upstream\n"
                "2026-03-21 08:12:02 ERROR [app] ConnectionError: "
                "Cannot reach database at 10.0.1.5:5432\n"
                "2026-03-21 08:12:03 WARN  [app] Retry 3/3 failed for db connection\n"
                "2026-03-21 08:12:04 ERROR [app] Service unhealthy – "
                "shutting down pod app-7b4f6c-xk9z2"
            )
        },
    )
    context: str | None = Field(
        default=None,
        description="Optional context about the system (e.g. infrastructure, recent changes)",
        json_schema_extra={
            "example": "Kubernetes cluster on AWS, recently scaled down RDS instances"
        },
    )


class PatternMatch(BaseModel):
    pattern: str = Field(description="Identified log pattern or anomaly")
    occurrences: int = Field(description="Number of times this pattern appears")
    severity: SeverityLevel = Field(description="Severity level of the pattern")


class RootCause(BaseModel):
    summary: str = Field(description="Brief summary of the root cause")
    detail: str = Field(description="Detailed explanation of the root cause")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0"
    )


class SuggestedFix(BaseModel):
    title: str = Field(description="Short title of the fix")
    description: str = Field(description="Detailed description of what to do")
    command: str | None = Field(
        default=None, description="Optional CLI command to apply the fix"
    )
    priority: str = Field(description="Priority: immediate, short-term, or long-term")


class LogAnalysisResponse(BaseModel):
    patterns: list[PatternMatch] = Field(description="Detected log patterns")
    root_cause: RootCause = Field(description="Identified root cause")
    suggested_fixes: list[SuggestedFix] = Field(description="Recommended fixes")
    summary: str = Field(description="Human-readable analysis summary")
