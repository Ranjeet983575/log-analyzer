from fastapi import FastAPI
from app.router import router

from app.config import get_settings, Settings

settings: Settings = get_settings()

app = FastAPI(
    title="AI Log Analyzer",
    description=(
        "AI-powered system log analyzer that identifies **root causes** and "
        "suggests **fixes** using LLM reasoning.\n\n"
        "### How to use\n"
        "1. Set `OPENAI_API_KEY` in the `.env` file.\n"
        "2. POST raw system logs to `/analyze`.\n"
        "3. Receive structured root-cause analysis with suggested fixes."
    ),
    version="0.2.0",
)

# Include router
app.include_router(router)


def start():
    """Entry-point for CLI script."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level,
        reload=True,
    )