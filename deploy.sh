#!/usr/bin/env bash
# Genesis — Cloud Run deployment script
#
# Usage:
#   First deploy (one-time setup + build):  ./deploy.sh --setup
#   Subsequent deploys:                      ./deploy.sh
#   Tear down:                               ./deploy.sh --destroy
#
# Prerequisites: gcloud CLI authenticated, .env present

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  echo "ERROR: .env not found. Run: cp .env.example .env and fill in values."
  exit 1
fi
set -a; source "$ROOT/.env"; set +a

# ── Config (override via env if needed) ───────────────────────────────────────
PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
REPO="genesis"
SA_NAME="genesis-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SERVICE_NAME="genesis-api"

LINEAR_API_KEY="${LINEAR_API_KEY:?LINEAR_API_KEY must be set in .env}"
LINEAR_TEAM_ID="${LINEAR_TEAM_ID:?LINEAR_TEAM_ID must be set in .env}"
GOOGLE_API_KEY="${GOOGLE_API_KEY:?GOOGLE_API_KEY must be set in .env}"
GOOGLE_CALENDAR_ID="${GOOGLE_CALENDAR_ID:-primary}"
GOOGLE_DRIVE_FOLDER_ID="${GOOGLE_DRIVE_FOLDER_ID:-}"

# AlloyDB — set ALLOYDB_INSTANCE_URI in .env to override
ALLOYDB_INSTANCE_URI="${ALLOYDB_INSTANCE_URI:-projects/${PROJECT_ID}/locations/${REGION}/clusters/genesis/instances/genesis-primary}"
SESSION_DB_URL="${SESSION_DB_URL:-postgresql+asyncpg://postgres:${DB_PASSWORD:-changeme}@/genesis?host=/cloudsql/${PROJECT_ID}:${REGION}:genesis}"
# Toolbox runs inside the same container via start.sh — always localhost
MCP_TOOLBOX_CLOUD_URL="http://localhost:5000/mcp"

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { echo "  $*"; }
success() { echo "✓ $*"; }
section() { echo ""; echo "── $* ──────────────────────────────────────────────"; }

secret_exists() { gcloud secrets describe "$1" --project="$PROJECT_ID" &>/dev/null; }

# ── One-time setup ────────────────────────────────────────────────────────────
setup() {
  section "Setting up project: $PROJECT_ID ($REGION)"

  gcloud config set project "$PROJECT_ID"

  # Enable APIs
  section "Enabling APIs"
  gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    alloydb.googleapis.com \
    aiplatform.googleapis.com \
    secretmanager.googleapis.com \
    docs.googleapis.com \
    calendar-json.googleapis.com \
    drive.googleapis.com
  success "APIs enabled"

  # Artifact Registry
  section "Artifact Registry"
  if gcloud artifacts repositories describe "$REPO" --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    info "Repository '$REPO' already exists — skipping"
  else
    gcloud artifacts repositories create "$REPO" \
      --repository-format=docker \
      --location="$REGION" \
      --project="$PROJECT_ID"
    success "Created repository: $REPO"
  fi

  # Service account
  section "Service Account"
  if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" &>/dev/null; then
    info "Service account $SA_EMAIL already exists — skipping"
  else
    gcloud iam service-accounts create "$SA_NAME" \
      --display-name="Genesis Cloud Run SA" \
      --project="$PROJECT_ID"
    success "Created service account: $SA_EMAIL"
  fi

  # IAM roles for the service account
  section "IAM roles → $SA_NAME"
  for role in \
    roles/aiplatform.user \
    roles/alloydb.client \
    roles/secretmanager.secretAccessor \
    roles/run.invoker \
    roles/cloudsql.client; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:$SA_EMAIL" \
      --role="$role" \
      --condition=None \
      --quiet
    info "$role"
  done
  success "IAM roles granted"

  # Cloud Build SA permissions
  section "Cloud Build SA permissions"
  PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
  CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
  for role in \
    roles/run.admin \
    roles/iam.serviceAccountUser \
    roles/artifactregistry.writer; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:$CB_SA" \
      --role="$role" \
      --condition=None \
      --quiet
    info "$role → $CB_SA"
  done
  success "Cloud Build permissions granted"

  # Secret Manager
  section "Secret Manager"

  # DB user
  if secret_exists "genesis-db-user"; then
    info "Secret genesis-db-user already exists — skipping"
  else
    echo -n "${DB_USER:-postgres}" | gcloud secrets create genesis-db-user \
      --data-file=- --project="$PROJECT_ID"
    success "Created secret: genesis-db-user"
  fi

  # DB password
  if secret_exists "genesis-db-password"; then
    info "Secret genesis-db-password already exists — skipping"
  else
    echo -n "${DB_PASSWORD:-changeme}" | gcloud secrets create genesis-db-password \
      --data-file=- --project="$PROJECT_ID"
    success "Created secret: genesis-db-password"
  fi

  # Linear API key
  if secret_exists "genesis-linear-key"; then
    info "Secret genesis-linear-key already exists — skipping"
  else
    echo -n "$LINEAR_API_KEY" | gcloud secrets create genesis-linear-key \
      --data-file=- --project="$PROJECT_ID"
    success "Created secret: genesis-linear-key"
  fi

  # Google API key
  if secret_exists "genesis-google-api-key"; then
    info "Secret genesis-google-api-key already exists — skipping"
  else
    echo -n "$GOOGLE_API_KEY" | gcloud secrets create genesis-google-api-key \
      --data-file=- --project="$PROJECT_ID"
    success "Created secret: genesis-google-api-key"
  fi

  # Grant SA access to each secret
  section "Secret IAM → $SA_NAME"
  for secret in genesis-db-user genesis-db-password genesis-linear-key genesis-google-api-key; do
    gcloud secrets add-iam-policy-binding "$secret" \
      --member="serviceAccount:$SA_EMAIL" \
      --role="roles/secretmanager.secretAccessor" \
      --project="$PROJECT_ID" \
      --quiet
    info "$secret"
  done
  success "Secret access granted"

  section "Setup complete"
  echo ""
  echo "  Run './deploy.sh' to build and deploy."
  echo ""
}

# ── Build + deploy ─────────────────────────────────────────────────────────────
deploy() {
  # SHORT_SHA is only auto-set when triggered from a connected repo.
  # When using `gcloud builds submit` manually we must pass it ourselves.
  SHORT_SHA=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)

  section "Building and deploying: $SERVICE_NAME"
  info "Project:  $PROJECT_ID"
  info "Region:   $REGION"
  info "Image:    ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE_NAME}:${SHORT_SHA}"
  echo ""

  gcloud builds submit "$ROOT" \
    --config="$ROOT/cloudbuild.yaml" \
    --project="$PROJECT_ID" \
    --substitutions=\
"SHORT_SHA=${SHORT_SHA},\
_REGION=${REGION},\
_REPO=${REPO},\
_SA_EMAIL=${SA_EMAIL},\
_ALLOYDB_INSTANCE_URI=${ALLOYDB_INSTANCE_URI},\
_MCP_TOOLBOX_URL=${MCP_TOOLBOX_CLOUD_URL},\
_LINEAR_TEAM_ID=${LINEAR_TEAM_ID},\
_GOOGLE_CALENDAR_ID=${GOOGLE_CALENDAR_ID},\
_GOOGLE_DRIVE_FOLDER_ID=${GOOGLE_DRIVE_FOLDER_ID}"

  section "Deployed"
  SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format="value(status.url)")
  echo ""
  echo "  ADK Web UI → ${SERVICE_URL}"
  echo "  API docs   → ${SERVICE_URL}/docs"
  echo ""
}

# ── Destroy ───────────────────────────────────────────────────────────────────
destroy() {
  section "Destroying Cloud Run service: $SERVICE_NAME"
  read -r -p "  This will delete the Cloud Run service. Continue? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

  gcloud run services delete "$SERVICE_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --quiet
  success "Service deleted: $SERVICE_NAME"
}

# ── Entry point ───────────────────────────────────────────────────────────────
case "${1:-}" in
  --setup)   setup; deploy ;;
  --destroy) destroy ;;
  "")        deploy ;;
  *)
    echo "Usage: $0 [--setup | --destroy]"
    echo ""
    echo "  (no flag)  Build and deploy to Cloud Run"
    echo "  --setup    One-time infrastructure setup, then deploy"
    echo "  --destroy  Delete the Cloud Run service"
    exit 1
    ;;
esac
