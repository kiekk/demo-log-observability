# ai-bot

AI Incident Bot — Grafana Webhook 수신 + 코드 분석 + (Plan 3+) PR 생성 자동화.

## 개발 모드 (host 실행, 인프라는 docker)

```bash
# 상위 디렉토리의 인프라 기동
cd ..
docker compose --profile demo up -d postgres buggy-service alloy loki grafana

# 봇만 host에서 실행
cd ai-bot
uv sync
WEBHOOK_TOKEN=dev-token LOKI_URL=http://localhost:3100 \
GITHUB_REPO=kiekk/demo-buggy-service \
GITHUB_REPO_URL=https://github.com/kiekk/demo-buggy-service.git \
SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL ../.env | cut -d= -f2-) \
DB_PATH=/tmp/ai-bot-dev.db DRY_RUN=true \
REPO_CACHE_DIR=/tmp/ai-bot-repos WORKTREE_DIR=/tmp/ai-bot-wt \
uv run uvicorn ai_bot.main:app --reload --port 8090
```

## 테스트

```bash
uv run pytest -v
```

## Docker 풀세트 기동

```bash
cd ..
docker compose --profile demo up -d --build
```
