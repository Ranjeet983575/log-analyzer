# AI-Powered Log Analyzer

An AI-powered system log analyzer built with **FastAPI** that identifies root causes and suggests fixes using LLM reasoning (OpenAI GPT-4o).

## Features

- **Pattern Recognition** — Detects recurring error patterns, severity levels, and anomalies
- **Root Cause Analysis** — LLM-powered deep analysis with confidence scoring
- **Suggested Fixes** — Prioritised fixes (immediate → short-term → long-term) with optional CLI commands
- **Swagger UI** — Interactive API docs at `/docs`
- **API Key Auth** — Secured via `X-API-Key` header

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- OpenAI API key

### Setup

```bash
# Clone and enter project
cd log-analyzer

# Copy env file and add your OpenAI key
cp .env.example .env
# Edit .env → set OPENAI_API_KEY=sk-...

# Install dependencies with uv
uv sync

# Run the server
uv run uvicorn app.main:app --reload
```

The server starts at **http://localhost:8000**.

### Swagger UI

Open **http://localhost:8000/docs** to test the API interactively.

1. Click the **Authorize** 🔒 button
2. Enter your OpenAI API key in the `X-API-Key` field
3. Try the `/analyze` endpoint with sample logs

## API Endpoints

| Method | Path       | Description                  |
|--------|------------|------------------------------|
| GET    | `/health`  | Health check                 |
| POST   | `/analyze` | Analyze logs (requires auth) |

### Example Request

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_OPENAI_API_KEY" \
  -d '{
    "logs": "2026-03-21 08:12:01 ERROR [nginx] upstream timed out (110: Connection timed out)\n2026-03-21 08:12:02 ERROR [app] ConnectionError: Cannot reach database at 10.0.1.5:5432\n2026-03-21 08:12:03 WARN [app] Retry 3/3 failed for db connection\n2026-03-21 08:12:04 ERROR [app] Service unhealthy – shutting down pod app-7b4f6c-xk9z2",
    "context": "Kubernetes cluster on AWS, recently scaled down RDS instances"
  }'
```

### Example Response

```json
{
  "patterns": [
    {"pattern": "Connection timeout to database", "occurrences": 3, "severity": "error"},
    {"pattern": "Pod shutdown due to health check failure", "occurrences": 1, "severity": "critical"}
  ],
  "root_cause": {
    "summary": "Database connection failure due to RDS scale-down",
    "detail": "The RDS instance was recently scaled down, causing connection pool exhaustion...",
    "confidence": 0.87
  },
  "suggested_fixes": [
    {
      "title": "Scale RDS back up",
      "description": "Restore the previous RDS instance size to handle current connection load",
      "command": "aws rds modify-db-instance --db-instance-identifier mydb --db-instance-class db.r5.xlarge --apply-immediately",
      "priority": "immediate"
    }
  ],
  "summary": "The logs indicate a cascading failure originating from database connectivity issues..."
}
```

## Project Structure

```
log-analyzer/
├── app/
│   ├── __init__.py
│   ├── config.py       # Settings from .env
│   ├── models.py       # Pydantic request/response models
│   ├── analyzer.py     # Pattern extraction + LLM analysis
│   └── main.py         # FastAPI app, routes, auth
├── .env                # Your API keys (git-ignored)
├── .env.example        # Template for .env
├── pyproject.toml      # Project metadata & dependencies
└── README.md
```
