# Demo Guide

다른 사람에게 (또는 면접관에게) 데모를 시연하기 위한 체크리스트.

---

## 0. 사전 준비 (1회)

### 환경변수 (`.env` 루트에)
```bash
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...               # repo scope 필수
GITHUB_REPO=kiekk/demo-buggy-service
GITHUB_REPO_URL=https://github.com/kiekk/demo-buggy-service.git
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
WEBHOOK_TOKEN=$(openssl rand -hex 16)
AI_BOT_WEBHOOK_URL=http://ai-bot:8090/webhooks/grafana
HIKARI_MAX_POOL=10
DRY_RUN=false
DAILY_COST_CAP_USD=5
```

### 외부 셋업
- `demo-buggy-service` GitHub 레포 + (권장) main branch protection (`Require PR review`)
- Slack 채널 `#ai-bot-demo` + Incoming Webhook

### 의존성
- Docker 20.10+, Docker Compose v2
- (자동 설치) Node.js 20 + `@anthropic-ai/claude-code` — ai-bot Dockerfile에서 이미지에 포함

---

## 1. 풀세트 기동 (시연 직전)

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git submodule update --init --recursive
docker compose --profile demo down -v   # 깨끗하게 시작
docker compose --profile demo up -d --build
sleep 90                                  # buggy-service Flyway + ai-bot 초기화
```

### 확인
```bash
docker compose ps                         # 모든 서비스 Up
curl http://localhost:8090/health         # ai-bot {"status":"ok",...}
curl http://localhost:8081/actuator/health # buggy-service UP
open http://localhost:3000                # Grafana (admin/admin)
```

Grafana → Dashboards → "AI Bot Overview" / "App Logs Overview" 패널 확인.

---

## 2. 시나리오 시연

각 시나리오 약 3분 (k6 90초 + alert 평가 30초 + LLM 분석 1~2분).

### 시연 흐름 (공통)

1. 트리거 명령 실행
2. Grafana Explore: `{service="demo-buggy-service"} | json | level="ERROR"`
3. 90~120초 후 Slack 채널에서 단계별 메시지 (`🚨 → 🔍 → ✅/🔎/⚙️/🔇`)
4. GitHub Issue/PR 확인
5. (시간 있으면) Grafana "AI Bot Overview"에서 카테고리 분포 변화

### 시나리오 1 — CODE_BUG (NPE)
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js
```
**기대**: Slack `✅ PR 생성됨`, GitHub Draft PR (null check 추가)

### 시나리오 2 — CODE_BUG (0 나눗셈)
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-2-divzero.js
```
**기대**: Slack `✅ PR`, PR에 `if (items == 0)` 가드

### 시나리오 3 — CODE_BUG (Enum)
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-3-enum.js
```
**기대**: Slack `✅ PR`, PR에 try-catch 또는 화이트리스트

### 시나리오 4 — DATA_ANOMALY (빈 city)
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-4-data.js
```
**기대**:
- Slack `🔎 데이터 조사 필요`
- GitHub Issue **only** (PR 없음), 본문에 검증 SQL + LogQL

### 시나리오 5 — INFRA_ISSUE (HikariCP 풀)
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-5-dbpool.js
```
**기대**:
- Slack `⚙️ 인프라 점검 필요`
- GitHub Issue **only**, 본문에 점검 체크리스트

### 시나리오 6 — BENIGN_ERROR (broken pipe)
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-6-benign.js
```
**기대**:
- Slack `🔇 노이즈 에러 처리 PR 생성됨`
- GitHub: 좁은 PR (ExceptionHandler) + 별도 alert rule 조정 제안 Issue

---

## 3. 시연 후 정리

### 비용 확인
```bash
docker compose exec ai-bot sqlite3 /data/ai-bot.db \
    "SELECT date(created_at), SUM(cost_usd), SUM(input_tokens), SUM(output_tokens) FROM llm_usage GROUP BY date(created_at);"
```

### Cleanup
```bash
docker compose --profile demo down
# 완전 정리 (DB 포함):
# docker compose --profile demo down -v
```

### Draft PR 처리
- 머지하지 말 것 (의도적 버그 보존)
- 다음 시연 전 GitHub에서 일괄 close
- ai-bot SQLite 비우면 dedup 초기화:
  `docker compose exec ai-bot rm /data/ai-bot.db && docker compose restart ai-bot`

---

## 4. 자주 묻는 질문 (FAQ)

**Q. AI가 잘못 고치면?**
A. PR은 항상 Draft + `human-review-required` 라벨. 사람이 검토 후 머지. 자동 머지 금지.

**Q. 비용 폭주?**
A. 일일 cap (`DAILY_COST_CAP_USD=5`). 초과 시 신규 분석 자동 거절 + Slack 경고.

**Q. 무한 트리거 안 함?**
A. dedup 윈도우 (`DEDUP_WINDOW_MINUTES=10`)로 같은 fingerprint 10분 내 1회만 분석. BENIGN_ERROR는 24시간 cooldown.

**Q. 회사 도입 가능?**
A. 데모 단순화 vs 회사 기획서 차이 있음 (Kafka MSK 미사용, GitHub Issue를 Jira로 교체 필요, Anthropic API key를 Bedrock로 교체 등). spec 문서 참고.

---

## 5. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| ai-bot이 webhook 받았는데 분석 시작 안 함 | dedup이 동일 fingerprint 차단 중 | 10분 대기 또는 SQLite 비우기 |
| 분석이 INSUFFICIENT_CONTEXT만 반환 | 컨텍스트 부족 또는 commit_sha=unknown | LogFetcher fallback 동작 확인. `docker compose logs ai-bot` 로 도구 호출 흐름 검토 |
| PR 생성 실패 | GITHUB_TOKEN 권한 부족 | repo scope 전체 확인. private repo는 fine-grained PAT보다 classic PAT 권장 |
| Slack 알림 안 옴 | SLACK_WEBHOOK_URL 잘못됨 | `curl -X POST $SLACK_WEBHOOK_URL -d '{"text":"test"}'` 검증 |
| Alloy가 ai-bot 로그 수집 안 함 | alloy.hcl keep regex 미반영 | `docker compose restart alloy` |
| Grafana에 ai-bot 패널 비어있음 | Loki 인덱싱 지연 또는 service 라벨 누락 | Grafana Explore에서 `{service="ai-bot"}` 쿼리로 직접 확인 |

---

## 6. 시연 시간 예산

| 단계 | 시간 |
|---|---|
| 배경 설명 (spec 요약) | 3분 |
| 풀세트 기동 + Grafana 한 바퀴 | 3분 |
| 시나리오 1~3 (CODE_BUG, 빠른 시연) | 각 2분 × 3 = 6분 |
| 시나리오 4 (DATA_ANOMALY, 차별화 강조) | 4분 |
| 시나리오 5 (INFRA_ISSUE) | 3분 |
| 시나리오 6 (BENIGN_ERROR, 클로징) | 3분 |
| Q&A | 5분 |
| **합계** | **~27분** |

빠른 버전 (10분): 시나리오 1 + 4 + 6만.
