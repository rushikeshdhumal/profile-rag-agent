# Multi-stage image for local Compose and Oracle / production VMs
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    STATIC_DIR=/app/frontend/dist \
    PORT=7860 \
    HOST=0.0.0.0 \
    HF_HOME=/data/hf_cache \
    FASTEMBED_CACHE_PATH=/data/hf_cache \
    ANONYMIZED_TELEMETRY=False \
    CHROMA_TELEMETRY_DISABLED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY --from=frontend-build /frontend/dist /app/frontend/dist
COPY examples /app/examples

RUN mkdir -p /data

EXPOSE 7860
CMD ["sh", "-c", "cd /app/backend && uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-7860}"]
