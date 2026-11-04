# Build context = repository root (see docker-compose.yml)

# ---- stage 1: React frontend (Vite)
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- stage 2: Django API (+ serves the built SPA via whitenoise)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/srv/frontend

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev poppler-utils ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY backend/ /app
COPY --from=frontend /fe/dist /srv/frontend
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
