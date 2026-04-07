# Stage 1: Dependencies (cached unless manifests change)
FROM debian:13.4-slim AS deps

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential nodejs npm python3 python3-pip python3-dev \
        ripgrep ffmpeg gcc libffi-dev curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/hermes

# Copy only dependency manifests
COPY pyproject.toml requirements.txt package.json package-lock.json ./
COPY scripts/whatsapp-bridge/package.json scripts/whatsapp-bridge/package-lock.json ./scripts/whatsapp-bridge/

# Install all dependencies (heaviest layer — cached across deploys)
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages && \
    npm install --prefer-offline --no-audit && \
    npx playwright install --with-deps chromium --only-shell && \
    cd /opt/hermes/scripts/whatsapp-bridge && \
    npm install --prefer-offline --no-audit && \
    npm cache clean --force

# Stage 2: Application
FROM deps AS production

# Copy application code (fast — deps already installed)
COPY . /opt/hermes

# Editable install (no-deps — uses cached deps from stage 1)
RUN pip install --no-cache-dir --no-deps -e ".[all]" --break-system-packages

# Fix Windows CRLF line endings
RUN sed -i 's/\r$//' /opt/hermes/docker/entrypoint.sh && \
    chmod +x /opt/hermes/docker/entrypoint.sh

ENV HERMES_HOME=/opt/data

# Healthcheck: verify the hermes process is alive (works for any gateway type)
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD pgrep -f "hermes" > /dev/null || exit 1

ENTRYPOINT [ "/opt/hermes/docker/entrypoint.sh" ]
CMD [ "gateway" ]
