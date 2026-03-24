import json
import re
from collections import Counter
from typing import List

from langchain_core.prompts import ChatPromptTemplate  # v0.2 ONLY
from langchain_groq import ChatGroq

from app.config import Settings
from app.models import (
    LogAnalysisResponse,
    PatternMatch,
    RootCause,
    SeverityLevel,
    SuggestedFix,
)

# -------------------------------
# System prompt for LLM
# -------------------------------
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
- Return ONLY valid JSON, no markdown fences or extra text.
"""

# -------------------------------
# Local pattern extraction
# -------------------------------
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


def _extract_patterns(logs: str) -> List[PatternMatch]:
    lines = [line.strip() for line in logs.strip().splitlines() if line.strip()]
    normalized = []
    for line in lines:
        n = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*\S*", "<TIMESTAMP>", line)
        n = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b", "<IP>", n)
        n = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>", n, flags=re.I)
        n = re.sub(r"\b[a-z]+-[a-z0-9]+-[a-z0-9]+\b", "<POD>", n, flags=re.I)
        normalized.append(n)

    counter = Counter(normalized)
    patterns: List[PatternMatch] = []
    for pattern_text, count in counter.most_common(10):
        # Find original lines matching this normalized pattern
        matching_originals = [orig for orig, norm in zip(lines, normalized) if norm == pattern_text]
        severities = [_classify_severity(orig) for orig in matching_originals]
        severity = max(severities, key=lambda s: s.value) if severities else SeverityLevel.UNKNOWN
        patterns.append(PatternMatch(pattern=pattern_text, occurrences=count, severity=severity))
    return patterns


# -------------------------------
# LangChain-based log analyzer (v0.2+ FIXED)
# -------------------------------
async def analyze_logs_langchain(logs: str, context: str | None, settings: Settings) -> LogAnalysisResponse:
    """
    Analyze system logs using LangChain v0.2+ with ChatGroq.
    """
    # 1️⃣ Extract local patterns
    local_patterns = _extract_patterns(logs)
    local_pattern_summary = json.dumps([p.model_dump() for p in local_patterns], indent=2)

    # 2️⃣ v0.2: ChatPromptTemplate.from_messages() with tuples
    chat_prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", """LOGS:
{logs}

ADDITIONAL CONTEXT:
{context}

LOCAL PATTERN SUMMARY (for reference):
{local_patterns}
""")
    ])

    # 3️⃣ Format to messages
    messages = chat_prompt.format_messages(
        logs=logs,
        context=context or "",
        local_patterns=local_pattern_summary
    )

    # 4️⃣ ChatGroq
    chat = ChatGroq(
        model="llama3-groq-70b-8192-tool-use-preview",  # JSON-friendly
        temperature=0.2,
        api_key=getattr(settings, 'groq_api_key', None)  # Safe access
    )

    # 5️⃣ v0.2: invoke() + .content
    response = await chat.invoke(messages)
    raw_text = response.content or "{}"

    # 6️⃣ Parse JSON safely, with debug logging
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        # Log the raw response for debugging
        print("[LLM JSONDecodeError] Raw response:\n", raw_text)
        raise ValueError(f"LLM returned invalid JSON: {e}\nRaw: {raw_text}")

    # Check for required fields
    if not isinstance(data, dict) or "patterns" not in data or "root_cause" not in data or "suggested_fixes" not in data:
        print("[LLM Response Error] Missing required fields. Raw response:\n", raw_text)
        raise ValueError(f"LLM response missing required fields: {data}")

    try:
        return LogAnalysisResponse(
            patterns=[PatternMatch(**p) for p in data.get("patterns", [])],
            root_cause=RootCause(**data.get("root_cause", {})),
            suggested_fixes=[SuggestedFix(**f) for f in data.get("suggested_fixes", [])],
            summary=data.get("summary", ""),
        )
    except Exception as e:
        print("[Model Construction Error] Data:", data)
        raise ValueError(f"Failed to construct response model: {e}\nData: {data}")