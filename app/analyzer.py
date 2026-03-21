import json
import re
from collections import Counter

from openai import AsyncOpenAI

from app.config import Settings
from app.models import (
    LogAnalysisResponse,
    PatternMatch,
    RootCause,
    SeverityLevel,
    SuggestedFix,
)

SYSTEM_PROMPT = """You are an expert DevOps/SRE engineer specializing in log analysis and incident response.

Analyze the provided system logs and return a JSON response with this exact structure:
{
  "patterns": [
    {"pattern": "description of pattern", "occurrences": <int>, "severity": "critical|error|warning|info"}
  ],
  "root_cause": {
    "summary": "one-line root cause",
    "detail": "detailed explanation with evidence from the logs",
    "confidence": <float 0.0-1.0>
  },
  "suggested_fixes": [
    {"title": "short title", "description": "what to do and why", "command": "optional shell command or null", "priority": "immediate|short-term|long-term"}
  ],
  "summary": "human-readable paragraph summarizing the analysis"
}

Rules:
- Base your analysis strictly on the log evidence provided.
- Identify error patterns, frequency, timing correlations, and cascading failures.
- Rank fixes by priority (immediate → short-term → long-term).
- If confidence is low, say so honestly.
- Return ONLY valid JSON, no markdown fences or extra text."""


def _classify_severity(line: str) -> SeverityLevel:
    upper = line.upper()
    if "CRITICAL" in upper or "FATAL" in upper or "PANIC" in upper:
        return SeverityLevel.CRITICAL
    if "ERROR" in upper or "FAIL" in upper:
        return SeverityLevel.ERROR
    if "WARN" in upper:
        return SeverityLevel.WARNING
    if "INFO" in upper or "DEBUG" in upper:
        return SeverityLevel.INFO
    return SeverityLevel.UNKNOWN


def _extract_patterns(logs: str) -> list[PatternMatch]:
    """Quick local pattern extraction before LLM call — gives a baseline."""
    lines = [line.strip() for line in logs.strip().splitlines() if line.strip()]
    # Normalise numbers, IPs, UUIDs to group similar lines
    normalised: list[str] = []
    for line in lines:
        n = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*\S*", "<TIMESTAMP>", line)
        n = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b", "<IP>", n)
        n = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>", n, flags=re.I)
        n = re.sub(r"\b[a-z]+-[a-z0-9]+-[a-z0-9]+\b", "<POD>", n, flags=re.I)
        normalised.append(n)

    counter = Counter(normalised)
    patterns: list[PatternMatch] = []
    for pattern_text, count in counter.most_common(10):
        # Determine severity from original lines that match this pattern
        severity = SeverityLevel.UNKNOWN
        for orig, norm in zip(lines, normalised):
            if norm == pattern_text:
                severity = _classify_severity(orig)
                break
        patterns.append(PatternMatch(pattern=pattern_text, occurrences=count, severity=severity))
    return patterns


async def analyze_logs(logs: str, context: str | None, settings: Settings) -> LogAnalysisResponse:
    """Run local pattern extraction, then call the LLM for deep analysis."""
    local_patterns = _extract_patterns(logs)

    user_message = f"LOGS:\n{logs}"
    if context:
        user_message += f"\n\nADDITIONAL CONTEXT:\n{context}"
    user_message += f"\n\nLOCAL PATTERN SUMMARY (for reference):\n{json.dumps([p.model_dump() for p in local_patterns], indent=2)}"

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    response = await client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)

    return LogAnalysisResponse(
        patterns=[PatternMatch(**p) for p in data.get("patterns", [])],
        root_cause=RootCause(**data["root_cause"]),
        suggested_fixes=[SuggestedFix(**f) for f in data.get("suggested_fixes", [])],
        summary=data.get("summary", ""),
    )
