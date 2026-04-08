# Genesis

Google Cloud APAC Hackathon · ADK + MCP Toolbox + AlloyDB + Cloud Run

Paste a brain-dump. Genesis spins up a multi-agent pipeline that creates a Google Doc, a task list, and calendar events from it — all in your real Google Workspace, not mocks.

---

## Architecture

```
User (ADK Web UI)
      │
      ▼
Cloud Run ── FastAPI ── get_fast_api_app
                              │
                        ADK Runner
                              │
                    ┌─────────▼──────────┐
                    │   genesis_root     │  Gemini 2.5 Pro
                    │  (Root Agent)      │
                    └──┬──┬──┬──┬────────┘
                       │  │  │  │
            ┌──────────┘  │  │  └───────────┐
            ▼             ▼  ▼              ▼
      planner_agent  archivist  dispatcher  timekeeper
      (Gemini Pro)   (Flash)    (Flash)     (Flash)
      output_schema
      =ExtractedPlan
            │             │       │              │
            │         ┌───▼───────▼──────────────▼───┐
            │         │        MCP Toolbox            │
            │         │  create_google_doc            │
            │         │  Linear MCP (create_issue)   │
            │         │  create_calendar_event        │
            │         │  delete_* (saga rollback)     │
            │         └───────────────┬───────────────┘
            │                         │
            │                  Google Tools Server
            │                  (google-api-python-client)
            │                         │
            │              ┌──────────▼──────────┐
            │              │   Google Workspace  │
            │              │  Docs · Tasks · Cal │
            │              └─────────────────────┘
            │
            ▼
        AlloyDB (PostgreSQL + pgvector)
        ┌─────────────────────────────┐
        │ projects                    │
        │ tool_artifacts              │
        │ workflow_steps              │
        │ brain_dump_embeddings       │  ← semantic recall
        └─────────────────────────────┘
```

### Agent responsibilities

| Agent | Model | Role |
|---|---|---|
| `genesis_root` | Gemini 2.5 Pro | Orchestrator — enforces order, handles saga rollback |
| `planner_agent` | Gemini 2.5 Pro | Extracts `ExtractedPlan` (structured output) |
| `archivist_agent` | Gemini Flash | Creates Google Doc via MCP |
| `dispatcher_agent` | Gemini Flash | Creates Linear issues via Linear MCP |
| `timekeeper_agent` | Gemini Flash | Schedules Google Calendar events via MCP |

---

## Local Setup

### Prerequisites

- Python 3.12+
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
- [MCP Toolbox](https://github.com/googleapis/genai-toolbox) (`toolbox` on PATH)
- AlloyDB instance **or** local PostgreSQL for development

### 1. Install dependencies

```bash
uv sync
```

### 2. Authenticate

```bash
gcloud auth application-default login
```

### 3. Configure environment

```bash
cp .env.example .env69.
# Edit .env — set GOOGLE_CLOUD_PROJECT, DB credentials
```

### 4. Apply database schema

```bash
# With AlloyDB Auth Proxy running on 127.0.0.1:5432:
psql -h 127.0.0.1 -U postgres -d genesis -f db/schema.sql
```

### 5. Start everything

```bash
./start.sh
```

Opens:
- **ADK Web UI** → http://localhost:8080
- **API docs** → http://localhost:8080/docs

---

## Demo

**Quick start:** paste `demo/brain_dump.txt` into the ADK UI chat and watch the agents fire.

---

## Cloud Run Deployment

```bash
# Set your project
export PROJECT_ID=your-project-id

# Build and deploy
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=\
_ALLOYDB_INSTANCE_URI="projects/$PROJECT_ID/locations/us-central1/clusters/genesis/instances/genesis-primary",\
_MCP_TOOLBOX_URL="http://toolbox-sidecar:5000/sse",\
_SESSION_DB_URL="postgresql+asyncpg://postgres:PASSWORD@/genesis?host=/cloudsql/$PROJECT_ID:us-central1:genesis"
```

### GCP services required

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  alloydb.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com
```

### Service account permissions

```bash
SA="genesis-sa@$PROJECT_ID.iam.gserviceaccount.com"
for role in \
  roles/aiplatform.user \
  roles/alloydb.client \
  roles/secretmanager.secretAccessor \
  roles/run.invoker; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA" --role="$role"
done
```

---

## API Reference

The ADK web UI is the primary interface. Additional endpoints:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/ask/{session_id}` | Semantic recall from brain-dump via pgvector |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/ready` | Readiness probe (Cloud Run) |

---

## Project Structure

```
genesis/
├── agent.py                  # ADK entry point (exports root_agent)
├── agents/
│   ├── root_agent.py         # Orchestrator + planner_agent
│   ├── archivist_agent.py    # Google Docs sub-agent
│   ├── dispatcher_agent.py   # Linear issues sub-agent
│   ├── timekeeper_agent.py   # Google Calendar sub-agent
│   └── schemas.py            # ExtractedPlan + shared Pydantic models
├── mcp/
│   ├── tools.yaml            # MCP Toolbox tool definitions
│   └── google_tools_server.py  # FastAPI wrapper for Google APIs
├── db/
│   ├── schema.sql            # AlloyDB schema (pgvector)
│   ├── repo.py               # Async SQLAlchemy repository
│   └── embeddings.py         # Vertex AI embeddings + semantic recall
├── api/
│   ├── main.py               # get_fast_api_app entry point
│   └── routes.py             # /ask + health endpoints
├── demo/
│   └── brain_dump.txt        # Seeded demo input
├── start.sh                  # Local dev startup script
├── Dockerfile
├── cloudbuild.yaml
└── pyproject.toml
```

---

## Codelabs Referenced

1. [Deploy an ADK agent to Cloud Run](https://codelabs.developers.google.com/codelabs/production-ready-ai-with-gc/5-deploying-agents/deploy-an-adk-agent-to-cloud-run)
2. [Build agents with ADK (foundation)](https://codelabs.developers.google.com/devsite/codelabs/build-agents-with-adk-foundation)
3. [ADK + MCP + BigQuery + Maps](https://codelabs.developers.google.com/adk-mcp-bigquery-maps)
4. [MCP Toolbox for BigQuery dataset](https://codelabs.developers.google.com/mcp-toolbox-bigquery-dataset)
5. [Quick AlloyDB setup](https://codelabs.developers.google.com/quick-alloydb-setup)
6. [Gemini + Flash on AlloyDB](https://codelabs.developers.google.com/gemini-3-flash-on-alloydb-sustainability-app)
