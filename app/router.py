from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form

from app.analyzer import analyze_logs
from app.analyzer_langchain import analyze_logs_langchain
from app.config import Settings, get_settings
from app.models import LogAnalysisRequest, LogAnalysisResponse

router = APIRouter()


def get_verified_settings(settings: Settings = Depends(get_settings)) -> Settings:
    """Ensure the GROQ API key is configured."""
    if not settings.groq_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfigured: GROQ_API_KEY is not set in .env",
        )
    return settings


# Health-check
@router.get("/health", tags=["Health"])
async def health_check():
    """Health-check endpoint."""
    return {"status": "ok"}


@router.post(
    "/analyze",
    response_model=LogAnalysisResponse,
    tags=["Analysis"],
    summary="Analyze system logs",
    description="Submit raw system logs and receive AI-powered root-cause analysis with suggested fixes.",
)
async def analyze(
    request: LogAnalysisRequest,
    settings: Settings = Depends(get_verified_settings),
) -> LogAnalysisResponse:
    try:
        result = await analyze_logs(request.logs, request.context, settings)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM analysis failed: {exc}",
        )
    return result

@router.post(
    "/analyze-langchain",
    response_model=LogAnalysisResponse,
    tags=["Analysis"],
    summary="Analyze system logs",
    description="Submit raw system logs and receive AI-powered root-cause analysis with suggested fixes.",
)
async def analyze(
    request: LogAnalysisRequest,
    settings: Settings = Depends(get_verified_settings),
) -> LogAnalysisResponse:
    try:
        result = await analyze_logs_langchain(request.logs, request.context, settings)
        return result
    except Exception as exc:
        # More specific error details for debugging
        detail = f"LLM analysis failed: {str(exc)}"
        if "GROQ" in str(exc).upper():
            detail += " Check your GROQ_API_KEY and quota."
        elif "JSON" in str(exc).upper():
            detail += " Model returned invalid JSON format."
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )

# Analyze logs from file upload
@router.post(
    "/analyze/upload",
    response_model=LogAnalysisResponse,
    tags=["Analysis"],
    summary="Analyze logs from file upload",
    description="Upload a log file and optionally provide context. No JSON escaping needed.",
)
async def analyze_upload(
    file: UploadFile = File(..., description="Log file to analyze"),
    context: str = Form(None, description="Optional context about the system"),
    settings: Settings = Depends(get_verified_settings),
) -> LogAnalysisResponse:
    logs = (await file.read()).decode("utf-8", errors="replace")
    try:
        result = await analyze_logs(logs, context, settings)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM analysis failed: {exc}",
        )
    return result