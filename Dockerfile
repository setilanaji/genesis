FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install MCP Toolbox binary
ARG TOOLBOX_VERSION=0.31.0
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL \
    "https://storage.googleapis.com/genai-toolbox/v${TOOLBOX_VERSION}/linux/amd64/toolbox" \
    -o /usr/local/bin/toolbox \
 && chmod +x /usr/local/bin/toolbox

WORKDIR /app

# Install Python dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# Copy source
COPY . .

ENV PORT=8080
EXPOSE 8080

# start.sh handles: Google Tools Server (8001) → MCP Toolbox (5000) → Genesis API (8080)
CMD ["./start.sh"]
