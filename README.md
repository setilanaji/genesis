# Genesis

Google Cloud APAC Hackathon · ADK + MCP Toolbox + AlloyDB + Cloud Run

Paste a brain-dump. Genesis spins up a multi-agent pipeline that creates a Google Doc, a Linear task board, and Google Calendar events — all in your real workspace, not mocks.

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
      (Gemini Flash) (Flash)    (Flash)     (Flash)
      output_schema
      =ExtractedPlan
            │             │       │              │
            │         ┌───▼───────▼──────────────▼───┐
            │         │        MCP Toolbox            │
            │         │  create_google_doc            │
            │         │  create_calendar_event        │
            │         │  delete_* (saga rollback)     │
            │         └───────────────┬───────────────┘
            │                         │
            │                 Google Tools Server
            │                 (google-api-python-client)
            │                         │
            │              ┌──────────▼──────────┐
            │              │   Google Workspace  │
            │              │  Docs · Calendar    │
            │              └─────────────────────┘
            │
            │         Linear MCP (hosted)
            │         https://mcp.linear.app/mcp
            │         create_issue · search_issues
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
| `planner_agent` | Gemini Flash | Extracts `ExtractedPlan` (structured JSON output) |
| `archivist_agent` | Gemini Flash | Creates Google Doc via MCP Toolbox |
| `dispatcher_agent` | Gemini Flash | Creates Linear issues via Linear hosted MCP |
| `timekeeper_agent` | Gemini Flash | Schedules Google Calendar events via MCP Toolbox |

---

## Local Setup

### Prerequisites

| Tool | Install |
|---|---|
| Python 3.12 (not 3.13) | `pyenv install 3.12` or system package |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) | See link |
| [MCP Toolbox](https://github.com/googleapis/genai-toolbox/releases) | Binary on `$PATH` as `toolbox` |
| PostgreSQL client (`psql`) | For running schema migrations |

---

## Step 1 — Google Cloud setup

### 1a. Authenticate with Application Default Credentials

```bash
gcloud auth application-default login
```

This grants the Google Tools Server (Docs + Calendar) access to your Google Workspace via OAuth.

> **Scopes used:** `documents`, `calendar`, `drive.file`

### 1b. Enable required APIs

```bash
gcloud services enable \
  docs.googleapis.com \
  calendar-json.googleapis.com \
  drive.googleapis.com \
  aiplatform.googleapis.com \
  alloydb.googleapis.com \
  secretmanager.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

### 1c. Get your Project ID and Location

```bash
gcloud config get project      # e.g. my-project-123
gcloud config get compute/region   # e.g. us-central1
```

These go into `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` in your `.env`.

---

## Step 2 — Linear setup

### 2a. Create a Linear API key

1. Go to [linear.app/account/api-keys](https://linear.app/account/api-keys)
2. Click **Create key**, name it `genesis`, copy the value — it looks like `lin_api_xxxxxxxxxxxxxxxxxxxx`
3. Set `LINEAR_API_KEY` in `.env`

### 2b. Get your Linear Team ID

```bash
curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ teams { nodes { id name } } }"}' \
  | python3 -m json.tool
```

Copy the `id` (UUID format) for the team where issues should be created.
Set `LINEAR_TEAM_ID` in `.env`.

---

## Step 3 — Google Calendar ID (optional)

By default Genesis uses your primary calendar (`primary`). To target a specific calendar:

1. Open [Google Calendar](https://calendar.google.com) → Settings gear → select a calendar
2. Scroll to **Calendar ID** — looks like `xxxx@group.calendar.google.com` or your Gmail for primary
3. Set `GOOGLE_CALENDAR_ID` in `.env`

If omitted, `primary` is used automatically.

---

## Step 4 — Google Drive folder (optional)

To save all generated Docs into a specific folder:

1. Open the folder in Google Drive
2. Copy the folder ID from the URL: `https://drive.google.com/drive/folders/<FOLDER_ID>`
3. Set `GOOGLE_DRIVE_FOLDER_ID` in `.env`

If omitted, Docs are created in the root of My Drive.

---

## Step 5 — Database setup

### Local development (plain PostgreSQL)

```bash
# Install PostgreSQL if needed (macOS)
brew install postgresql@15 && brew services start postgresql@15

# Create database
createdb genesis

# Apply schema (enables pgvector extension)
psql -d genesis -f db/schema.sql
```

Set in `.env`:
```
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=
DB_NAME=genesis
```

### AlloyDB (Cloud Run / production)

Start the [AlloyDB Auth Proxy](https://cloud.google.com/alloydb/docs/auth-proxy/overview) on `127.0.0.1:5432`, then apply the schema the same way. For Cloud Run, set `ALLOYDB_INSTANCE_URI` instead of `DB_HOST/PORT` (see `.env.example`).

---

## Step 6 — MCP Toolbox

Download the latest `toolbox` binary from [github.com/googleapis/genai-toolbox/releases](https://github.com/googleapis/genai-toolbox/releases) and place it on your `$PATH`:

```bash
# macOS example
chmod +x toolbox
mv toolbox /usr/local/bin/toolbox

# Verify
toolbox --version
```

`start.sh` launches Toolbox automatically, pointing it at `tools_server/tools.yaml` on port 5000.
The tools config proxies to the Google Tools Server running on port 8001.

---

## Step 7 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` with all values collected above:

```bash
# ── Google Cloud ──────────────────────────────────────────────────────────────
GOOGLE_CLOUD_PROJECT=your-project-id          # gcloud config get project
GOOGLE_CLOUD_LOCATION=us-central1             # gcloud config get compute/region
GOOGLE_GENAI_USE_VERTEXAI=true                # use Vertex AI (not AI Studio)

# Optional: path to service account key file (leave unset to use ADC from gcloud auth)
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

# ── Google Workspace ──────────────────────────────────────────────────────────
GOOGLE_CALENDAR_ID=primary                    # or specific calendar ID
# GOOGLE_DRIVE_FOLDER_ID=                     # optional: target folder for Docs

# ── Linear ────────────────────────────────────────────────────────────────────
LINEAR_API_KEY=lin_api_xxxxxxxxxxxxxxxxxxxx   # from linear.app/account/api-keys
LINEAR_TEAM_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxx  # from GraphQL query above

# ── Database (local PostgreSQL) ───────────────────────────────────────────────
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=
DB_NAME=genesis

# Cloud Run: use this instead of DB_HOST/PORT
# ALLOYDB_INSTANCE_URI=projects/PROJECT/locations/REGION/clusters/genesis/instances/genesis-primary

# ── ADK session storage ───────────────────────────────────────────────────────
# Local: SQLite is auto-created (no setting needed)
# Cloud Run: set to AlloyDB connection string
# SESSION_DB_URL=postgresql+asyncpg://postgres:PASSWORD@/genesis?host=/cloudsql/PROJECT:REGION:genesis

# ── MCP Toolbox ───────────────────────────────────────────────────────────────
MCP_TOOLBOX_URL=http://localhost:5000/mcp     # managed by start.sh
```

---

## Step 8 — Install Python dependencies

```bash
cd genesis
uv sync
```

---

## Step 9 — Run

```bash
./start.sh
```

`start.sh` starts three processes in order:

| Port | Process | Log |
|---|---|---|
| `8001` | Google Tools Server (Docs + Calendar) | `/tmp/genesis-tools.log` |
| `5000` | MCP Toolbox | `/tmp/genesis-toolbox.log` |
| `8080` | Genesis API + ADK Web UI | stdout |

Open:
- **ADK Web UI** → http://localhost:8080
- **API docs** → http://localhost:8080/docs

---

## Demo

Paste the contents of `demo/brain_dump.txt` into the ADK UI chat and watch all four agents fire in sequence.

---

## How the MCP connection works

```
ADK Agent
  └─ McpToolset(StreamableHTTPConnectionParams(url="http://localhost:5000/mcp"))
        │
        ▼
  MCP Toolbox (toolbox binary, port 5000)
  reads tools_server/tools.yaml
        │
        ▼  HTTP POST to http://localhost:8001
  Google Tools Server (uvicorn, port 8001)
  google-api-python-client + ADC credentials
        │
        ▼
  Google Docs API / Google Calendar API
```

For Linear, the dispatcher agent connects **directly** to Linear's hosted MCP:
```
dispatcher_agent
  └─ McpToolset(StreamableHTTPConnectionParams(
       url="https://mcp.linear.app/mcp",
       headers={"Authorization": "Bearer <LINEAR_API_KEY>"}
     ))
```

No local process needed for Linear — just the API key.

---

## Cloud Run Deployment

The build pipeline is defined in `cloudbuild.yaml`: it builds the Docker image, pushes it to Artifact Registry, and deploys to Cloud Run. Secrets are pulled from Secret Manager at deploy time.

### One-time setup

Run these once before the first deploy.

**Set your project:**
```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
gcloud config set project $PROJECT_ID
```

**Create the Artifact Registry repository:**
```bash
gcloud artifacts repositories create genesis \
  --repository-format=docker \
  --location=$REGION
```

**Create the service account:**
```bash
gcloud iam service-accounts create genesis-sa \
  --display-name="Genesis Cloud Run SA"
```

**Grant IAM roles:**
```bash
SA="genesis-sa@$PROJECT_ID.iam.gserviceaccount.com"
for role in \
  roles/aiplatform.user \
  roles/alloydb.client \
  roles/secretmanager.secretAccessor \
  roles/run.invoker \
  roles/cloudsql.client; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA" --role="$role"
done
```

**Store secrets in Secret Manager** (the cloudbuild.yaml pulls these at deploy time):
```bash
# Database credentials
echo -n "postgres"        | gcloud secrets create genesis-db-user     --data-file=-
echo -n "YOUR_DB_PASSWORD" | gcloud secrets create genesis-db-password --data-file=-

# Linear API key
echo -n "lin_api_xxxx"   | gcloud secrets create genesis-linear-key  --data-file=-
```

Grant the service account access to the secrets:
```bash
for secret in genesis-db-user genesis-db-password genesis-linear-key; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor"
done
```

**Grant Cloud Build permission to deploy:**
```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
CB_SA="$PROJECT_NUMBER@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CB_SA" --role="roles/run.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CB_SA" --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$CB_SA" --role="roles/artifactregistry.writer"
```

---

### Deploy

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
export LINEAR_TEAM_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx   # from Step 2b

gcloud builds submit --config cloudbuild.yaml \
  --substitutions=\
"_REGION=$REGION,\
_ALLOYDB_INSTANCE_URI=projects/$PROJECT_ID/locations/$REGION/clusters/genesis/instances/genesis-primary,\
_MCP_TOOLBOX_URL=http://localhost:5000/mcp,\
_SESSION_DB_URL=postgresql+asyncpg://postgres:PASSWORD@/genesis?host=/cloudsql/$PROJECT_ID:$REGION:genesis,\
_LINEAR_TEAM_ID=$LINEAR_TEAM_ID"
```

> **Note on `_MCP_TOOLBOX_URL`:** In Cloud Run, MCP Toolbox must run as a sidecar container or a separate Cloud Run service. For a quick deploy, you can run it as a second Cloud Run service and point this URL to it. Alternatively, for a single-container deploy, bundle Toolbox in the Dockerfile and run it on a different port.

What `cloudbuild.yaml` does:
1. Builds the Docker image (Python 3.12-slim + uv)
2. Pushes to `$REGION-docker.pkg.dev/$PROJECT_ID/genesis/genesis-api:$SHORT_SHA`
3. Deploys to Cloud Run with:
   - `--min-instances=1` (no cold starts)
   - `--allow-unauthenticated` (public ADK UI)
   - Env vars: `GOOGLE_CLOUD_PROJECT`, `ALLOYDB_INSTANCE_URI`, `LINEAR_TEAM_ID`, `MCP_TOOLBOX_URL`, `SESSION_DB_URL`
   - Secrets mounted: `DB_USER`, `DB_PASSWORD`, `LINEAR_API_KEY`

---

### Check the deployed service

```bash
gcloud run services describe genesis-api --region=$REGION \
  --format="value(status.url)"
```

Open the returned URL — it serves the ADK Web UI directly.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/ask/{session_id}` | Semantic recall from brain-dump via pgvector |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/ready` | Readiness probe (Cloud Run) |

---

## Project Structure

```
genesis/
├── agent.py                        # ADK entry point (exports root_agent)
├── agents/
│   ├── root_agent.py               # Orchestrator — calls all four sub-agents
│   ├── archivist_agent.py          # Google Docs sub-agent (MCP Toolbox)
│   ├── dispatcher_agent.py         # Linear issues sub-agent (Linear MCP)
│   ├── timekeeper_agent.py         # Google Calendar sub-agent (MCP Toolbox)
│   ├── schemas.py                  # ExtractedPlan + shared Pydantic models
│   └── retry_patch.py              # 429/503 exponential back-off for ADK
├── tools_server/
│   ├── tools.yaml                  # MCP Toolbox tool definitions
│   └── google_tools_server.py      # FastAPI wrapper for Google Docs + Calendar
├── db/
│   ├── schema.sql                  # AlloyDB schema (pgvector)
│   ├── repo.py                     # Async SQLAlchemy repository
│   └── embeddings.py               # Vertex AI embeddings + semantic recall
├── api/
│   ├── main.py                     # get_fast_api_app entry point
│   └── routes.py                   # /ask + health endpoints
├── demo/
│   └── brain_dump.txt              # Seeded demo input
├── .env.example                    # Template — copy to .env
├── start.sh                        # Local dev startup (3 processes)
├── Dockerfile
├── cloudbuild.yaml
└── pyproject.toml
```

---

## Troubleshooting

**`toolbox: command not found`**
Download the binary from the [releases page](https://github.com/googleapis/genai-toolbox/releases) and put it on `$PATH`.

**`google.auth.exceptions.DefaultCredentialsError`**
Run `gcloud auth application-default login` and make sure `GOOGLE_GENAI_USE_VERTEXAI=true` is set.

**Linear issues not created**
Verify `LINEAR_API_KEY` starts with `lin_api_` and `LINEAR_TEAM_ID` is the UUID (not the team slug). Use the GraphQL query in Step 2b to confirm.

**`relation "projects" does not exist`**
The database schema hasn't been applied. Run `psql -d genesis -f db/schema.sql`.

**`Extension "vector" not found`**
For local PostgreSQL: `brew install pgvector` then `CREATE EXTENSION vector;` in psql. For AlloyDB it's pre-installed.

**Docs created in wrong Google account**
ADC uses the account from `gcloud auth application-default login`. Run that command again and log in with the correct account.

---

## Codelabs Referenced

1. [Deploy an ADK agent to Cloud Run](https://codelabs.developers.google.com/codelabs/production-ready-ai-with-gc/5-deploying-agents/deploy-an-adk-agent-to-cloud-run)
2. [Build agents with ADK (foundation)](https://codelabs.developers.google.com/devsite/codelabs/build-agents-with-adk-foundation)
3. [ADK + MCP + BigQuery + Maps](https://codelabs.developers.google.com/adk-mcp-bigquery-maps)
4. [MCP Toolbox for BigQuery dataset](https://codelabs.developers.google.com/mcp-toolbox-bigquery-dataset)
5. [Quick AlloyDB setup](https://codelabs.developers.google.com/quick-alloydb-setup)
6. [Gemini + Flash on AlloyDB](https://codelabs.developers.google.com/gemini-3-flash-on-alloydb-sustainability-app)
