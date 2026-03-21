from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.analyzer import analyze_logs
from app.config import Settings, get_settings
from app.models import LogAnalysisRequest, LogAnalysisResponse

app = FastAPI(
    title="AI Log Analyzer",
    description=(
        "AI-powered system log analyzer that identifies **root causes** and "
        "suggests **fixes** using LLM reasoning.\n\n"
        "### How to use\n"
        "1. Obtain an API key (set `OPENAI_API_KEY` in `.env`).\n"
        "2. POST raw system logs to `/analyze`.\n"
        "3. Receive structured root-cause analysis with suggested fixes."
    ),
    version="0.1.0",
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> Settings:
    """Validate that the caller provided a matching API key."""
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfigured: OPENAI_API_KEY is not set in .env",
        )
    if not api_key or api_key != settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Pass your key via the X-API-Key header.",
        )
    return settings


@app.get("/health", tags=["Health"])
async def health_check():
    """Health-check endpoint."""
    return {"status": "ok"}


@app.post(
    "/analyze",
    response_model=LogAnalysisResponse,
    tags=["Analysis"],
    summary="Analyze system logs",
    description="Submit raw system logs and receive AI-powered root-cause analysis with suggested fixes.",
)
async def analyze(
    request: LogAnalysisRequest,
    settings: Settings = Depends(verify_api_key),
) -> LogAnalysisResponse:
    try:
        result = await analyze_logs(request.logs, request.context, settings)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM analysis failed: {exc}",
        )
    return result


def start():
    """Entry-point for `log-analyzer` CLI script."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level,
        reload=True,
    )
