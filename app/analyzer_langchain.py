import json
import re
from collections import Counter
from typing import List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.config import Settings
from app.models import SeverityLevel  # Keep your existing enum if defined

# -------------------------------
# COMPLETE PYDANTIC MODELS
# -------------------------------
class PatternMatch(BaseModel):
    """Identified log pattern."""
    pattern: str = Field(..., description="Normalized log pattern")
    occurrences: int = Field(..., ge=1, description="How many times it occurred")
    severity: SeverityLevel = Field(..., description="Severity level")

class RootCause(BaseModel):
    """Root cause analysis."""
    summary: str = Field(..., max_length=200, description="One-line root cause")
    detail: str = Field(..., max_length=1000, description="Detailed explanation with log evidence")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")

class SuggestedFix(BaseModel):
    """Recommended fix."""
    title: str = Field(..., max_length=100, description="Short title")
    description: str = Field(..., max_length=500, description="What to do and why")
    command: str | None = Field(None, description="Shell command or null")
    priority: str = Field(..., description="immediate|short-term|long-term")

class LogAnalysisResponse(BaseModel):
    """Complete log analysis response."""
    patterns: List[PatternMatch] = Field(..., description="Identified patterns")
    root_cause: RootCause = Field(..., description="Root cause analysis")
    suggested_fixes: List[SuggestedFix] = Field(default_factory=list, description="Recommended fixes")
    summary: str = Field(..., max_length=500, description="Human-readable summary")

# -------------------------------
# SYSTEM PROMPT
# -------------------------------
SYSTEM_PROMPT = """You are an expert DevOps/SRE engineer specializing in log analysis and incident response.

Analyze the provided system logs and respond using the EXACT JSON structure provided in the response schema.

Rules:
1. Base analysis STRICTLY on log evidence - no speculation
2. Identify error patterns, frequency, timing correlations, cascading failures
3. Use evidence from LOCAL PATTERNS section
4. Rank fixes: immediate → short-term → long-term
5. Confidence 0.0-1.0 based on evidence strength
6. Return ONLY valid JSON matching the schema exactly

CRITICAL: Your response MUST be parseable as the LogAnalysisResponse schema."""

# -------------------------------
# LOCAL PATTERN EXTRACTION
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
        matching_originals = [orig for orig, norm in zip(lines, normalized) if norm == pattern_text]
        severities = [_classify_severity(orig) for orig in matching_originals]
        severity = max(severities, key=lambda s: s.value) if severities else SeverityLevel.UNKNOWN
        patterns.append(PatternMatch(pattern=pattern_text, occurrences=count, severity=severity))
    return patterns

# -------------------------------
# BULLETPROOF FALLBACKS (unchanged)
# -------------------------------
def extract_json_safely(text: str) -> Dict[str, Any]:
    text = text.strip()
    text = re.sub(r'```(?:json)?\s*', '', text, flags=re.DOTALL)
    text = re.sub(r'\s*```', '', text, flags=re.DOTALL)
    json_match = re.search(r'\{[^{}]*"patterns"[^}]*\}', text, re.DOTALL)
    if json_match:
        text = json_match.group(0)
    text = re.sub(r'\n\s*\n', '\n', text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"[JSON FAIL] Raw: {repr(text[:300])}...")
        return fallback_response()

def fallback_response() -> Dict[str, Any]:
    return {
        "patterns": [],
        "root_cause": {"summary": "Analysis failed", "detail": "LLM returned invalid JSON", "confidence": 0.0},
        "suggested_fixes": [],
        "summary": "Log analysis unavailable due to parsing error"
    }

def safe_patterns(patterns_data: Any) -> List[PatternMatch]:
    if not patterns_data:
        return []
    result = []
    for p in patterns_data:
        try:
            if isinstance(p, dict) and "pattern" in p:
                severity = SeverityLevel.INFO
                if "severity" in p:
                    severity_str = str(p["severity"]).upper()
                    if "CRITICAL" in severity_str: severity = SeverityLevel.CRITICAL
                    elif "ERROR" in severity_str: severity = SeverityLevel.ERROR
                    elif "WARN" in severity_str: severity = SeverityLevel.WARNING
                result.append(PatternMatch(
                    pattern=str(p.get("pattern", "")),
                    occurrences=int(p.get("occurrences", 0)),
                    severity=severity
                ))
        except:
            continue
    return result

def safe_root_cause(root_cause_data: Any) -> RootCause:
    try:
        return RootCause(
            summary=str(root_cause_data.get("summary", "")),
            detail=str(root_cause_data.get("detail", "")),
            confidence=float(root_cause_data.get("confidence", 0.0))
        )
    except:
        return RootCause(summary="Error", detail="Invalid data", confidence=0.0)

def safe_fixes(fixes_data: Any) -> List[SuggestedFix]:
    if not fixes_data:
        return []
    result = []
    for f in fixes_data:
        try:
            if isinstance(f, dict) and "title" in f:
                result.append(SuggestedFix(
                    title=str(f.get("title", "")),
                    description=str(f.get("description", "")),
                    command=str(f.get("command", "")) if f.get("command") else None,
                    priority=str(f.get("priority", "short-term"))
                ))
        except:
            continue
    return result

# -------------------------------
# ✅ MAIN LANGCHAIN IMPLEMENTATION
# -------------------------------
async def analyze_logs_langchain(logs: str, context: str | None, settings: Settings) -> LogAnalysisResponse:
    """
    LangChain with structured output - bulletproof JSON parsing.
    """
    # 1️⃣ Local patterns
    local_patterns = _extract_patterns(logs)
    local_pattern_summary = json.dumps([p.model_dump() for p in local_patterns], indent=2)

    # 2️⃣ Messages
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"""
    LOGS:
    {logs}

    CONTEXT:
    {context or ''}

    LOCAL PATTERNS:
    {local_pattern_summary}
    """)
    ]

    # 3️⃣ LangChain model
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.0,
        api_key=settings.groq_api_key
    )

    # ✅ STRUCTURED OUTPUT - RETURNS LogAnalysisResponse DIRECTLY
    chain = llm.with_structured_output(LogAnalysisResponse)

    # 4️⃣ Try structured first, fallback to your robust parser
    try:
        result = await chain.ainvoke(messages)
        print(f"[SUCCESS] Analysis: {result.summary[:100]}...")
        return result
    except Exception as e:
        print(f"[STRUCTURED FAIL] {e} - Using fallback")
        # Your bulletproof fallback
        response = await llm.ainvoke(messages)
        raw_text = response.content or "{}"
        print(f"[FALLBACK DEBUG] Raw: {repr(raw_text[:300])}...")
        data = extract_json_safely(raw_text)
        return LogAnalysisResponse(
            patterns=safe_patterns(data.get("patterns")),
            root_cause=safe_root_cause(data.get("root_cause")),
            suggested_fixes=safe_fixes(data.get("suggested_fixes")),
            summary=str(data.get("summary", "Analysis complete (fallback)"))
        )