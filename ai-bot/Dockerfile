# Build stage - uv로 의존성 + venv 준비
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src

RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app /app
COPY alembic.ini /app/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# 데이터 디렉토리 (volume mount 예정)
RUN mkdir -p /data /data/repos /data/worktrees
ENV DB_PATH=/data/ai-bot.db
ENV REPO_CACHE_DIR=/data/repos
ENV WORKTREE_DIR=/data/worktrees

EXPOSE 8090

# 마이그레이션 자동 적용 후 서버 기동
CMD ["sh", "-c", "alembic upgrade head && uvicorn ai_bot.main:app --host 0.0.0.0 --port 8090"]
