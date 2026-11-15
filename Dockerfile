FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY deployment/serving-release.json deployment/serving-release.json
COPY scripts/fetch_serving.py scripts/fetch_serving.py
RUN python scripts/fetch_serving.py
RUN pip install --no-cache-dir uv==0.9.8
COPY pyproject.toml uv.lock ./
COPY baseline/ baseline/
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist frontend/dist/
ENV PATH="/app/.venv/bin:$PATH" BASELINE_DB="/app/data/releases/current/serving.duckdb" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
CMD ["sh", "-c", "uvicorn baseline.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
