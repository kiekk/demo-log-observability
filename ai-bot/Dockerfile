# Build stage
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src

RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.12-slim

# git + Node.js (Claude Code CLI 의존성)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app /app
COPY alembic.ini /app/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# 비 root 사용자 생성 (claude --dangerously-skip-permissions은 root 실행 불가)
RUN useradd -m -u 1001 aibot \
    && mkdir -p /data /data/repos /data/worktrees \
    && chown -R aibot:aibot /data /app \
    && git config --global --add safe.directory '*'

ENV DB_PATH=/data/ai-bot.db
ENV REPO_CACHE_DIR=/data/repos
ENV WORKTREE_DIR=/data/worktrees

USER aibot

EXPOSE 8090

CMD ["sh", "-c", "alembic upgrade head && uvicorn ai_bot.main:app --host 0.0.0.0 --port 8090"]
