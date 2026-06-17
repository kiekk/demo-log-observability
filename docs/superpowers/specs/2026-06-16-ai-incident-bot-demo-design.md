# AI Incident Bot — 모니터링 알림 기반 자동 코드 수정/PR 생성 데모

> 작성일: 2026-06-16
> 형식: 설계 문서 (spec)
> 관련 문서:
> - 기존 베이스: `../../../PROJECT.md`, `../../../README.md`
> - 회사(Waiker) 기획서 참고: `~/Documents/obsidian/docs/waiker/02-infra/ai-incident-automation-system-plan.md`

> Grafana Alert가 발화하면 AI 봇이 배포된 시점의 소스코드를 분석하고,
> 원인 카테고리에 따라 PR을 만들거나 검증 쿼리를 첨부한 Issue를 생성한다.

---

## 1. 목적과 관객

세 가지 목적을 동시에 만족시키는 데모를 만든다.

1. **개인 학습** — Claude Agent SDK + 관측성 스택 + GitOps 자동화 연결 체험
2. **포트폴리오/면접 시연** — GitHub PR 링크를 실제로 보여줄 수 있는 살아있는 데모
3. **회사(Waiker) PoC** — 회사 기획서(`ai-incident-automation-system-plan.md`)를 작은 규모로 검증

목적이 셋이지만 우선순위는 **시연 가능성 > 회사 정렬 > 학습 깊이** 순이다. 즉 데모로서 한 번에 띄우고 한 번에 작동하는 것을 최우선으로 한다.

---

## 2. 컨텍스트

### 2.1 이미 있는 자산 (재사용)

`demo-log-observability/` 디렉토리에 다음이 동작 검증 완료된 상태로 존재한다.

- Spring Boot (Kotlin) 데모 앱 (루트 `src/main/...`): `/api/hello`, `/api/slow`, `/api/error`, `/api/burst`
- JSON 로그 + `request_id` MDC + logstash-logback-encoder
- Grafana Alloy (Docker stdout 수집) → Loki → Grafana 파이프라인
- k6 시나리오 3종 (smoke / steady / spike)
- Grafana Alert rule "High Error Log Rate" — Spike 시 실제 발화 확인

이 자산을 **확장**한다. 새 레포를 만들지 않는다.

### 2.2 두 개의 Spring Boot 앱 — 역할 분리

이번 데모에는 Spring Boot 앱이 **두 개** 존재한다. 혼동 방지를 위해 명확히 분리한다.

| 앱 | 위치 | 역할 |
|---|---|---|
| **기존 demo-api** | demo-log-observability 루트 `src/main/...` | 관측성 파이프라인(Alloy/Loki/Grafana) 검증용. 이번 데모에서는 **사용하지 않음** (기존 PROJECT.md의 smoke/steady/spike 시나리오 보존용으로만 유지) |
| **신규 demo-buggy-service** | 별도 GitHub 레포 (서브모듈로 마운트) | AI 봇이 분석/수정 대상으로 삼는 의도적 버그가 심긴 앱. 시나리오 1~6의 실제 트래픽 대상 |

데모 시연 시에는 **demo-buggy-service만 docker-compose로 띄운다**. 기존 demo-api는 옵션 (이전 관측성 데모를 재현할 때만 사용).

### 2.3 회사 기획서 (참고만)

Waiker 사내에는 Kafka MSK + Python FastAPI + Claude API + Jira + GitLab MR을 사용하는 정교한 AI 인시던트 자동화 시스템 기획서가 존재한다. 이 데모는 그 기획서의 **단순화된 학습/검증 버전**이며, 다음 차이가 있다.

| 항목 | 회사 기획서 | 본 데모 |
|---|---|---|
| 알림 전달 | Slack → Webhook → Spring Gateway → Kafka MSK | Grafana Webhook → 직접 HTTP |
| LLM 통합 | anthropic SDK 직접 호출 + 직접 컨텍스트 조립 | Claude Agent SDK (자율 도구 사용) |
| Git 호스팅 | GitLab self-host | GitHub public |
| 이슈 트래커 | Jira Cloud | GitHub Issue |
| 로그 저장소 | AWS CloudWatch | Loki |
| 메시지 브로커 | Kafka MSK | 없음 (직접 HTTP) |
| 알림 채널 | Slack (사내) | Slack (개인 워크스페이스) |

데모는 회사 기획과 다음을 공유한다.

- "Core 시스템과 AI 분석 시스템의 비동기 격리" 원칙 (단, Kafka 대신 HTTP)
- confidence threshold 0.7 게이팅
- 10분 dedup 윈도우
- 분석 결과 카테고리 분기

---

## 3. 확정된 결정 사항

| # | 결정 | 근거 |
|---|---|---|
| 1 | 목적 = 학습 + 포트폴리오 + 회사 PoC 동시 | 사용자 명시 |
| 2 | 기존 `demo-log-observability` 디렉토리 확장 | 이미 검증된 Alert 파이프라인 재사용 |
| 3 | 알림 트리거 = Grafana Webhook → AI 봇 HTTP | 데모 단순성 |
| 4 | PR 대상 = 별도 GitHub 토이 레포 `demo-buggy-service` | 면접 시연 임팩트, 무한 루프 회피 |
| 5 | LLM 통합 = Claude Agent SDK (Python) | 자율 도구 사용, 포트폴리오 임팩트 |
| 6 | 시연 시나리오 = 6개 (4개 카테고리 모두 커버) | 잘 되는 케이스 + 정직한 거부 케이스 함께 시연 |
| 7 | 외부 통합 = GitHub PR + GitHub Issue + Slack | 회사 정렬 (Slack) + 데모 깔끔함 |
| 8 | AI 봇 스택 = Python 3.12 + FastAPI + Claude Agent SDK | 회사 PoC 정렬, AI/ML 생태계 표준 |
| 9 | Root cause 카테고리 = CODE_BUG / DATA_ANOMALY / INFRA_ISSUE / INSUFFICIENT_CONTEXT / **BENIGN_ERROR** | DATA_ANOMALY / BENIGN_ERROR는 사용자 요청 추가 |
| 10 | DATA_ANOMALY 케이스에 검증 SQL + LogQL 첨부 | 사용자 요청 |
| 11 | BENIGN_ERROR(broken pipe 등)는 좁은 범위 PR(ExceptionHandler + 로그 레벨 다운그레이드) + alert rule 조정은 본문 제안만 (자동 수정 금지) | 사용자 요청 |

---

## 4. 아키텍처

```
                  ┌─────────────────────────────────────────┐
                  │  GitHub (별도 레포)                     │
                  │  - demo-buggy-service (의도적 버그)     │
                  │    └─ git submodule + 빌드 시 SHA 임베드│
                  └────────────────┬────────────────────────┘
                                   │ git clone (호스트 캐시)
                                   ▼
[demo-log-observability 단일 디렉토리]
┌─────────────────────────────────────────────────────────────────┐
│  ┌──────────────┐    HTTP    ┌──────────────────────┐           │
│  │ k6 loadgen   │───────────▶│ demo-buggy-service   │──┐        │
│  │ 시나리오 6   │            │ Spring Boot Kotlin   │  │ JDBC   │
│  └──────────────┘            │ - MDC에 commit_sha   │  ▼        │
│                              │ - JSON 로그          │ ┌───────┐ │
│                              │ - JPA + HikariCP     │ │postgres│ │
│                              └──────────┬───────────┘ │(시나리│ │
│                                         │ stdout      │오 4/5)│ │
│                                         ▼             └───────┘ │
│                              ┌──────────────────────┐           │
│                              │ Alloy → Loki         │           │
│                              └──────────┬───────────┘           │
│                                         │                       │
│                              ┌──────────▼───────────┐           │
│                              │ Grafana              │           │
│                              │ - Alert rule         │           │
│                              │ - Contact Point:     │           │
│                              │   Webhook → ai-bot   │           │
│                              └──────────┬───────────┘           │
│                                         │ POST /webhooks/grafana│
│                                         ▼                       │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ ai-bot/ (신규)                                         │     │
│  │ Python 3.12 + FastAPI + Claude Agent SDK               │     │
│  │  Webhook → Orchestrator → Analyzer (Agent loop)        │     │
│  │     ├─ LogFetcher (Loki)                               │     │
│  │     ├─ RepoManager (git worktree at commit_sha)        │     │
│  │     ├─ GitHubClient (Issue/PR)                         │     │
│  │     ├─ SlackNotifier                                   │     │
│  │     └─ StateDB (SQLite)                                │     │
│  └────────────────────────┬───────────────────────────────┘     │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            ▼
            ┌──────────────────────────────┐
            │  GitHub demo-buggy-service   │
            │  - Issue + PR (Fixes #N)     │
            └──────────────────────────────┘
            ┌──────────────────────────────┐
            │  Slack #ai-bot-demo          │
            │  - 단계별 진행 메시지        │
            └──────────────────────────────┘
```

---

## 5. 컴포넌트 (ai-bot 내부)

| 컴포넌트 | 책임 | 입력 | 출력 |
|---|---|---|---|
| `WebhookReceiver` | Grafana Alert webhook 수신, Bearer 토큰 검증, dedup, `IncidentEvent` 생성 | Grafana JSON | `IncidentEvent` |
| `Orchestrator` | 파이프라인 조립 (LogFetch → Analyzer → GitHub → Slack), 상태 추적, graceful 실패 처리 | `IncidentEvent` | `AnalysisResult` |
| `LogFetcher` | Loki HTTP API로 `request_id` 기반 로그 체인 + 동일 에러 최근 N건 수집 | `commit_sha`, `request_id` | `LogContext` |
| `RepoManager` | bare clone 캐시 → `git worktree add <path> <sha>` 으로 배포 시점 코드 마운트, 분석 후 정리 | `commit_sha` | worktree 디렉토리 경로 |
| `Analyzer` | Claude Agent SDK 루프. 도구로 코드/스키마 탐색 → 카테고리 분류 + 결과 보고 | worktree path + `LogContext` | `AnalysisResult` |
| `GitHubClient` | Issue 생성 → 브랜치 생성 → 패치 커밋 → PR(Draft) 생성 | `AnalysisResult` | Issue #, PR # |
| `SlackNotifier` | 단계별 메시지 (감지/분석중/완료/거부), 카테고리별 메시지 차별화 | 단계 이벤트 | Slack 메시지 |
| `StateDB` | SQLite. `incidents`, `analysis_runs`, `llm_usage` 테이블 | run state | persisted |

---

## 6. 데이터 플로우

### 6.1 정상 케이스 (CODE_BUG)

```
T+0s    k6 시나리오-1 → app /api/users/999/profile → NPE
T+0s    로그: {"level":"ERROR","commit_sha":"abc123","request_id":"r-1",
              "exception":"NullPointerException at UserService.kt:42"}
T+0~5s  Alloy → Loki
T+30s   Grafana Alert Pending → 1분 후 Firing
T+90s   POST /webhooks/grafana → ai-bot
T+91s   WebhookReceiver: 토큰 검증 → dedup 통과 → IncidentEvent
T+91s   Slack: "🚨 에러 감지 - demo-buggy-service @ abc123"
T+92s   LogFetcher: request_id로 로그 체인 + 동일 에러 최근 N건 수집
T+93s   RepoManager: git worktree add /tmp/wt-r-1 abc123
T+93s   Slack: "🔍 분석 시작 - Claude Agent가 코드를 탐색합니다"
T+93s~  Analyzer (Claude Agent SDK 루프):
          tool: read_file("UserService.kt") → 42번째 줄 확인
          tool: grep("getAddress") → 호출처 추적
          tool: git_log("UserService.kt") → 최근 변경
          tool: propose_patch({file, old, new})
          tool: report_finding(category=CODE_BUG, confidence=0.85, ...)
T+2~3분 GitHubClient:
          1. Issue #12: "[AI] NullPointerException in UserService.getAddress"
          2. branch: ai-fix/issue-12
          3. commit: "fix: add null check (Fixes #12)"
          4. PR #13 (Draft, label: human-review-required)
T+2~3분 Slack: "✅ PR #13 생성됨 (confidence 0.85, $0.42, 2분 15초)"
```

### 6.2 거부 케이스 (INSUFFICIENT_CONTEXT)

```
... Analyzer 탐색 후 ...
report_finding(category=INSUFFICIENT_CONTEXT, confidence=0.45,
               root_cause="동시성 의심, 다른 서비스 로그 필요")
→ patch 없음. Issue만 생성 (label: needs-human-review)
→ Slack: "⚠️ 분석 불가 - 추가 컨텍스트 필요. Issue #N"
```

### 6.3 데이터 이상 케이스 (DATA_ANOMALY)

```
... Analyzer 탐색 후 ...
- 코드 path는 정상으로 판단
- read_db_schema로 addresses 테이블 구조 확인
- 가설: addresses.city = '' (빈 문자열) 데이터 정합성 문제
report_finding(
  category=DATA_ANOMALY, confidence=0.82,
  data_hypothesis="addresses.city 빈 문자열 (user_id 100~200)",
  verification_sql=[...3개...],
  verification_logql=[...3개...]
)
→ Issue 생성 (PR 없음). Issue 본문에 가설 + SQL + LogQL + 조치 우선순위 포함
→ Slack: "🔎 데이터 조사 필요 - Issue #N (검증 쿼리 첨부)"
```

### 6.4 인프라 이상 케이스 (INFRA_ISSUE)

```
... Analyzer 탐색 후 ...
- 코드 정상, SQLTransientConnectionException 패턴 다수
report_finding(
  category=INFRA_ISSUE, confidence=0.78,
  root_cause="HikariCP 풀 고갈 추정",
  infra_checklist=["HikariCP active=max 확인", "RDS connections 그래프 확인",
                   "슬로우 쿼리 확인", "동시 요청 수 확인"],
  related_metrics=["sum by (mdc_endpoint) (rate(...))"]
)
→ Issue + Slack: "⚙️ 인프라 점검 필요 - Issue #N"
```

### 6.5 양성 에러 케이스 (BENIGN_ERROR)

```
... Analyzer 탐색 후 ...
- 에러 위치는 streaming response 작성 중 IOException
- stack trace 패턴: ClientAbortException at OutputStream.write()
- 비즈니스 로직 정상, 클라이언트 disconnect로 판단
- propose_patch: GlobalExceptionHandler 추가 + 로그 레벨 INFO로
report_finding(
  category=BENIGN_ERROR, confidence=0.88,
  root_cause="클라이언트 측 disconnect로 인한 broken pipe — 비즈니스 로직 정상",
  alert_rule_proposal="exception_class!=ClientAbortException를 LogQL에 추가 제안"
)
→ 좁은 PR 생성 (label: noise-reduction)
→ Issue 본문에 alert rule 조정 제안 첨부 (자동 적용 X)
→ Slack: "🔇 노이즈 에러 처리 PR #N 생성 (ClientAbortException 핸들러 추가)"
```

---

## 7. Commit SHA 추적

배포된 시점의 정확한 코드를 분석하기 위한 핵심 메커니즘.

**(1) 빌드 시 git-properties 임베드** — `gradle-git-properties` 플러그인으로 jar 안에 `git.properties` 포함

**(2) 앱 시작 시 환경 노출** — `@Value("${git.commit.id.abbrev:unknown}")`

**(3) MDC 자동 주입** — `RequestIdFilter`에 `MDC.put("commit_sha", commitShaProvider.sha)` 추가. 모든 로그 라인에 자동 포함

**(4) Grafana Alert group by** — `sum by (commit_sha, service) (...)` 형태로 commit_sha가 webhook payload `commonLabels`에 들어가도록 설정

**(5) AI 봇이 worktree 생성** — bare clone은 1회만, 매 분석마다 `git worktree add <path> <sha>` 후 분석. 완료 시 worktree remove

### 데모 단순화

`demo-buggy-service` 레포는 main 브랜치 선형 진행으로 두고, 시나리오마다 `git tag scenario-N`을 박아둔다. 시연자는 `git checkout scenario-N && docker compose up --build app`으로 새 SHA로 배포된 척 환경을 만든다.

---

## 8. Root Cause 분류 + AnalysisResult 스키마

```python
class AnalysisResult(BaseModel):
    category: Literal[
        "CODE_BUG", "DATA_ANOMALY", "INFRA_ISSUE",
        "INSUFFICIENT_CONTEXT", "BENIGN_ERROR"
    ]
    confidence: float  # 0.0~1.0
    root_cause: str

    # CODE_BUG / BENIGN_ERROR일 때 (PR 생성 후보)
    patch: Patch | None = None

    # DATA_ANOMALY일 때 필수
    data_hypothesis: str | None = None
    verification_sql: list[str] = []
    verification_logql: list[str] = []

    # INFRA_ISSUE일 때 필수
    infra_checklist: list[str] = []
    related_metrics: list[str] = []

    # BENIGN_ERROR일 때 (Issue 본문에 제안만, 자동 적용 X)
    alert_rule_proposal: str | None = None
```

### PR 생성 조건 — 카테고리별 행동 매트릭스

| 카테고리 | confidence ≥ 0.7 | confidence < 0.7 | PR 라벨 |
|---|---|---|---|
| `CODE_BUG` | **PR 생성** (patch 필수) | Issue만 | `human-review-required` |
| `BENIGN_ERROR` | **PR 생성** (ExceptionHandler + 로그 레벨) | Issue만 (제안 사항만) | `noise-reduction`, `human-review-required` |
| `DATA_ANOMALY` | Issue + 검증 SQL/LogQL | Issue + 가설만 | (PR 없음) |
| `INFRA_ISSUE` | Issue + 체크리스트 | Issue + 가설만 | (PR 없음) |
| `INSUFFICIENT_CONTEXT` | (해당 없음) | Issue만 (추가 정보 요청) | (PR 없음) |

**PR 생성 결정 로직** (의사 코드):

```python
def should_create_pr(r: AnalysisResult) -> bool:
    if r.confidence < 0.7:
        return False
    if r.category == "CODE_BUG" and r.patch is not None:
        return True
    if r.category == "BENIGN_ERROR" and r.patch is not None:
        return True
    return False
```

**중요**: BENIGN_ERROR PR도 항상 Draft + `human-review-required`. AI가 진짜 중요한 에러를 noise로 오판할 위험이 있으므로 사람의 명시적 머지가 필수.

### Analyzer가 사용하는 도구 (Agent SDK)

| 도구 | 설명 |
|---|---|
| `read_file(path)` | worktree 안의 파일 읽기. allowlist 디렉토리 외 차단 |
| `grep(pattern, path?)` | 코드 검색 |
| `git_log(path?, limit=10)` | 최근 변경 이력 |
| `git_diff(sha1, sha2, path?)` | 변경 비교 |
| `read_db_schema(table?)` | `db/migration/*.sql` 또는 JPA Entity 읽기 (운영 DB 직접 연결 X) |
| `propose_patch(file, old, new)` | 패치 후보 등록. 단일 파일 + 30라인 이하만 허용 |
| `report_finding(category, ...)` | 최종 결과 보고. Pydantic으로 카테고리별 필수 필드 validation |

---

## 9. 안전장치 (Guardrails)

| # | 장치 | 메커니즘 |
|---|---|---|
| 1 | PR auto-merge 금지 | Draft 상태로 생성, `human-review-required` 라벨 |
| 2 | Confidence threshold 0.7 | 미달 시 patch 없이 Issue만 |
| 3 | Dedup 10분 윈도우 | `(service, commit_sha, error_class)` fingerprint로 |
| 4 | Dry-run 모드 | `DRY_RUN=true` 시 GitHub/Slack 호출을 콘솔 로그로 대체 |
| 5 | 일일 LLM 비용 cap | StateDB 합계 기반, 기본 $5 |
| 6 | 동시 분석 제한 | `asyncio.Semaphore(2)` |
| 7 | PR에 AI 표식 | 본문 상단 고정 문구 |
| 8 | 수정 범위 제한 | `propose_patch`는 단일 파일 + 30라인 이하 |
| 9 | Allowlist 디렉토리 | `src/main/` 외 도구 노출 차단 |
| 10 | Webhook 시그니처 검증 | `Authorization: Bearer ${WEBHOOK_TOKEN}` |
| 11 | **Alert rule 자동 수정 금지** | BENIGN_ERROR에서도 Grafana `alerts.yaml` 자체는 봇이 PR로 만들지 않음. Issue 본문에 제안만. 사람이 진짜 noise인지 판단 후 수동 적용 |
| 12 | **BENIGN_ERROR 오판 보호** | 동일 fingerprint가 24시간 내 BENIGN으로 분류된 적 있으면 두 번째 부터는 PR 만들지 않고 기존 Issue 참조만 (반복 noise PR 폭주 방지) |

---

## 10. 에러 핸들링

| 실패 지점 | 동작 | 사용자에게 보이는 것 |
|---|---|---|
| Loki 응답 없음/타임아웃 (10s) | 로그 없이 stack trace만으로 분석 진행 | Slack "⚠️ 로그 조회 실패, 제한된 컨텍스트로 분석 중" |
| Git fetch/worktree 실패 | 3회 재시도 → Issue만 생성 | Slack "❌ 코드 체크아웃 실패: {sha}", DB FAILED |
| Claude API 429/5xx | exponential backoff 3회 → Issue + Slack 알림 | Slack "⚠️ AI 분석 실패, 재시도 한도 초과" |
| GitHub API 오류 | 3회 재시도 → 패치를 DB에 저장 + Slack manual fallback 안내 | Slack "⚠️ PR 생성 실패. run_id: xxx" |
| Slack webhook 오류 | 메인 플로우 계속 (best-effort), DB 기록 | 없음 |
| Agent SDK 무한 루프 | `max_turns=20`, 전체 타임아웃 5분 | Slack "⚠️ 분석 타임아웃" |
| dedup 윈도우 내 재발화 | 기존 Issue에 댓글 (`재발화 N회`), 새 PR 안 만듦 | Slack "🔁 기존 인시던트 #N 재발" |

---

## 11. State DB 스키마 (SQLite)

```sql
CREATE TABLE incidents (
    id INTEGER PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    service TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    error_class TEXT NOT NULL,
    request_id TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    occurrence_count INTEGER DEFAULT 1,
    github_issue_number INTEGER,
    UNIQUE(fingerprint)
);

CREATE TABLE analysis_runs (
    id INTEGER PRIMARY KEY,
    incident_id INTEGER REFERENCES incidents(id),
    status TEXT NOT NULL,   -- PENDING/ANALYZING/CREATING_PR/COMPLETED/FAILED/REJECTED
    category TEXT,
    confidence REAL,
    root_cause TEXT,
    pr_number INTEGER,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE TABLE llm_usage (
    id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES analysis_runs(id),
    model TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    tool_calls_count INTEGER,
    latency_ms INTEGER
);
```

---

## 12. 시연 시나리오 6개

각 시나리오는 `demo-buggy-service`에 별도 git tag로 분리한다.

**카테고리 커버리지**: CODE_BUG(3) / DATA_ANOMALY(1) / INFRA_ISSUE(1) / BENIGN_ERROR(1). `INSUFFICIENT_CONTEXT`는 별도 시나리오 없이 시나리오 4/5에서 confidence < 0.7로 떨어질 때 자연스럽게 발현(시스템 프롬프트에 그 분기를 명시).

| # | 시나리오 | 트리거 (k6) | 심어둘 버그 | 기대 결과 |
|---|---|---|---|---|
| 1 | NPE — null 체크 누락 | `GET /api/users/{id}/profile` (id=999) | `user.address.street` 호출 전 `user` null 체크 누락 | CODE_BUG / conf 0.85 / PR |
| 2 | 0 나눗셈 | `GET /api/cart/discount?items=0&total=100` | `total / items` 가드 없음 | CODE_BUG / conf 0.80 / PR |
| 3 | Enum 매핑 실패 | `POST /api/orders` body에 `"status":"LEGACY_TYPE"` | `OrderStatus.valueOf("LEGACY_TYPE")` 예외 | CODE_BUG / conf 0.75 / PR |
| 4 | 데이터 정합성 — 빈 city | `GET /api/orders/{id}/shipping` (특정 user 범위) | Flyway seed가 일부 row를 `city=''`로 삽입. 코드는 정상 | DATA_ANOMALY / conf 0.82 / Issue + 검증 쿼리 |
| 5 | DB 커넥션 풀 고갈 | k6 스파이크로 `GET /api/reports/heavy` 동시 200건 | endpoint가 트랜잭션 안에서 3초 sleep + JPA 쿼리. `HikariCP max=10` 풀 고갈 → `SQLTransientConnectionException` | INFRA_ISSUE / conf 0.78 / Issue + 체크리스트 |
| 6 | 클라이언트 disconnect (broken pipe) | k6에서 `GET /api/download/large` 호출 + `timeout: 50ms` | streaming response가 `OutputStream.write()` 중 클라이언트가 끊김 → `ClientAbortException`. 비즈니스 로직 정상 | BENIGN_ERROR / conf 0.88 / **PR 생성** (`ClientAbortExceptionHandler` 추가) + Issue 본문에 alert rule 조정 제안 |

### DATA_ANOMALY Issue 본문 템플릿 (시나리오 4 예시)

````markdown
## 🔎 데이터 이상 추정 — 코드 수정 불필요

**서비스**: demo-buggy-service @ `abc123f`
**에러**: NullPointerException at OrderService.kt:88

### 가설
`OrderService.calculateShipping()`는 `user.address.city`를 사용하지만,
사용자 ID 범위 `[100, 200]` 구간에서 `addresses.city`가 빈 문자열(`''`)로
저장되어 있는 것으로 추정. 코드의 null 체크는 정상이나 빈 문자열 체크는
누락되어 있음.

**판단 근거**: 동일 코드 path에서 user_id <100 요청은 성공, ≥100만 실패.

### ✅ 검증 SQL (운영 read-replica 권장)

**1) 영향 범위 측정**
```sql
SELECT
    COUNT(*) AS total_users,
    COUNT(*) FILTER (WHERE a.city IS NULL OR a.city = '') AS broken_users,
    ROUND(100.0 * COUNT(*) FILTER (WHERE a.city IS NULL OR a.city = '')
          / COUNT(*), 2) AS broken_pct
FROM users u
LEFT JOIN addresses a ON a.user_id = u.id
WHERE u.id BETWEEN 100 AND 200;
```

**2) 깨진 데이터 샘플**
```sql
SELECT a.id, a.user_id, a.street, a.city, a.created_at
FROM addresses a
WHERE a.user_id BETWEEN 100 AND 200
  AND (a.city IS NULL OR a.city = '' OR a.street IS NULL)
ORDER BY a.created_at DESC
LIMIT 20;
```

**3) 언제부터 깨졌는지 (마이그레이션/배포 시점 추적)**
```sql
SELECT
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*) FILTER (WHERE city = '' OR city IS NULL) AS broken_count,
    COUNT(*) AS total_count
FROM addresses
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY day
ORDER BY day DESC;
```

### ✅ 검증 LogQL

**1) 같은 요청 패턴의 다른 유저도 실패하는지**
```logql
sum by (mdc_request_id) (
  count_over_time(
    {job="spring-boot-demo"}
      | json | mdc_endpoint="/api/orders/shipping"
      | level="ERROR" [1h]
  )
)
```

**2) 실패 요청의 user_id 분포**
```logql
{job="spring-boot-demo"}
  | json | mdc_endpoint="/api/orders/shipping" | level="ERROR"
  | regexp `user_id=(?P<uid>\d+)`
  | line_format "{{.uid}}"
```

**3) 정상 vs 에러 응답 비율**
```logql
sum by (mdc_status) (
  count_over_time(
    {job="spring-boot-demo"}
      | json | mdc_endpoint="/api/orders/shipping" [1h]
  )
)
```

### 권장 조치 (우선순위 순)
1. **즉시**: 위 SQL #1로 영향 범위 측정
2. **임시 (코드)**: `if (city.isNullOrBlank())` 체크 추가 — 증상 완화일 뿐
3. **근본 (데이터)**: 깨진 row backfill 또는 default 정책
4. **재발 방지**: `CHECK (city <> '')` 제약 + 입력 validation

### ⚠️ 이 Issue는 코드 PR을 자동 생성하지 않았습니다
AI 분석 결과 코드 로직 자체에는 명백한 결함이 보이지 않습니다.
잘못된 코드 패치는 진짜 원인(데이터 정합성)을 가릴 수 있어
사람의 판단을 요청드립니다.

---
🤖 ai-bot (confidence: 0.82, category: DATA_ANOMALY)
Run: `run-id-7f2a` | Cost: $0.38 | Tool calls: 14
````

### BENIGN_ERROR PR + Issue 본문 템플릿 (시나리오 6 예시)

**PR 본문** (좁은 범위 코드 변경)

````markdown
## 🔇 노이즈 에러 처리 — ClientAbortException 핸들러 추가

> 🤖 This PR was generated by AI. Review carefully before merging.

**서비스**: demo-buggy-service @ `abc123f`
**카테고리**: BENIGN_ERROR (confidence: 0.88)

### 무엇을 바꿨나
1. `ClientAbortExceptionHandler` 신설 — `ClientAbortException`을 ERROR 대신 INFO 레벨로 로깅
2. 응답 작성 시도하지 않음 (이미 연결 끊김)

### 왜 코드 수정만으로 충분한가
이 에러는 클라이언트가 응답 받기 전에 연결을 끊은 정상적인 외부 조건입니다.
비즈니스 로직 결함이 아니며, 서버 상태도 정상입니다.
ERROR 로그로 남으면서 알림을 발화시켜 진짜 인시던트와 혼동되는 노이즈입니다.

### 영향 범위
- 변경 파일: 1개 (`ClientAbortExceptionHandler.kt` 신규)
- 변경 라인: 약 15라인
- 비즈니스 로직 영향: 없음
- 사용자 경험 영향: 없음 (서버가 응답 못 쓴 것은 마찬가지)

### ⚠️ 머지 전 확인 사항
- [ ] 이 예외가 정말 클라이언트 측 원인인지 (서버 응답이 너무 느려서 끊은 게 아닌지)
- [ ] streaming 외 endpoint에서도 동일 패턴이 있는지 (있다면 `@ControllerAdvice` 범위 검토)
- [ ] Issue #N의 alert rule 조정 제안도 검토

---
🤖 ai-bot (confidence: 0.88) | Run: `run-id-8b3c` | Cost: $0.31 | Tool calls: 9
````

**Issue 본문 — alert rule 조정 제안** (자동 적용 X)

````markdown
## 🔇 노이즈 에러 추정 — 알림 규칙 조정 권장

PR #N에서 `ClientAbortExceptionHandler`를 추가했지만, 다음 패턴이 추가로
발견되면 알림 규칙 자체도 조정하는 것이 좋습니다. **AI는 alert rule을
자동 수정하지 않습니다**.

### 검증 LogQL — 정말 noise인지 사람이 먼저 확인

**1) 최근 1주일 noise 비율**
\`\`\`logql
sum by (exception_class) (
  count_over_time(
    {job="spring-boot-demo"} | json | level="ERROR" [1w]
  )
)
\`\`\`

**2) ClientAbortException 발생 패턴 (시간대/endpoint별)**
\`\`\`logql
sum by (mdc_endpoint, hour) (
  count_over_time(
    {job="spring-boot-demo"}
      | json | exception_class="ClientAbortException" [1d]
  )
)
\`\`\`

### 조정 제안 (수동 적용)

\`\`\`yaml
# infra/grafana/provisioning/alerting/alerts.yaml
- title: AI Bot - High Error Log Rate
  query: |
    sum by (commit_sha, service) (
      count_over_time({job="spring-boot-demo"} | json
        | level="ERROR"
        | exception_class!="ClientAbortException"  # ← 추가 제안
        [5m])
    )
\`\`\`

### ⚠️ 적용 전 체크리스트
- [ ] LogQL #1 결과로 ClientAbortException이 전체 ERROR의 다수를 차지하는지
- [ ] 정말 클라이언트 측 원인인지 (서버 측 성능 문제로 클라이언트가 포기한 게 아닌지)
- [ ] 다른 운영자의 검토 (이 조정으로 진짜 인시던트를 놓칠 위험)

---
🤖 ai-bot (confidence: 0.88, category: BENIGN_ERROR)
Run: `run-id-8b3c` | Related PR: #N
````

---

## 13. 디렉토리 구조

`★` 표시가 신규. 기존 demo는 build.gradle.kts/src/이 루트에 평면 배치되어 있다 (별도 `app/` 디렉토리 X).

```
demo-log-observability/
├── README.md                          (확장: AI 봇 섹션 추가)
├── PROJECT.md                         (기존)
├── build.gradle.kts                   (기존 demo-api Spring Boot, 옵션 사용)
├── src/                               (기존 demo-api 코드, 옵션 사용)
├── docker-compose.yml                 ★ 확장: ai-bot + postgres + buggy-service profile
├── .env.example                       ★
│
├── demo-buggy-service/                ★ git submodule (별도 GitHub 레포)
│   ├── Dockerfile                     (multi-stage, JAR build)
│   ├── build.gradle.kts               (git-properties plugin)
│   ├── src/main/kotlin/com/example/buggy/
│   │   ├── BuggyServiceApplication.kt
│   │   ├── controller/                (UserController, CartController,
│   │   │                                OrderController, InventoryController,
│   │   │                                SlowController)
│   │   ├── service/                   (시나리오별 의도적 버그)
│   │   ├── domain/                    (User, Order, Address, Inventory,
│   │   │                                OrderStatus enum)
│   │   └── repository/                (JPA repos)
│   └── src/main/resources/
│       ├── application.yml            (HikariCP max=10, JDBC postgres)
│       └── db/migration/
│           ├── V1__init_schema.sql
│           └── V2__seed_data.sql      (시나리오 4용 깨진 row 포함)
│
├── ai-bot/                            ★
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── README.md
│   ├── .env.example
│   ├── src/ai_bot/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── webhook/{receiver.py, schemas.py}
│   │   ├── orchestrator.py
│   │   ├── analyzer/{agent.py, tools.py, prompts.py, result.py}
│   │   ├── services/{log_fetcher.py, repo_manager.py,
│   │   │             github_client.py, slack_notifier.py}
│   │   ├── db/{models.py, session.py, migrations/}
│   │   └── safety/{dedup.py, cost_guard.py, path_allowlist.py}
│   └── tests/{unit/, integration/, e2e/}
│
├── infra/
│   ├── loki/, alloy/ (기존)
│   ├── postgres/                      ★
│   │   └── init.sql                   (DB 생성, demo-buggy-service가 Flyway로 스키마 적용)
│   ├── grafana/
│   │   ├── provisioning/
│   │   │   ├── datasources/, dashboards/ (기존)
│   │   │   └── alerting/
│   │   │       ├── alerts.yaml        ★ 확장: commit_sha + service group by + webhook
│   │   │       ├── contactpoints.yaml ★ 확장: ai-bot webhook
│   │   │       └── policies.yaml
│   │   └── dashboards/
│   │       ├── app-logs-overview.json (기존)
│   │       └── ai-bot-overview.json   ★ run 성공/실패, 비용, 카테고리 분포
│   └── loadgen/k6/
│       ├── smoke.js, steady.js, spike.js (기존, 보존만)
│       └── scenario-{1..6}.js         ★
│
└── docs/
    ├── ARCHITECTURE.md                ★
    ├── DEMO_GUIDE.md                  ★
    └── superpowers/specs/
        └── 2026-06-16-ai-incident-bot-demo-design.md  (이 문서)
```

### demo-buggy-service 통합 방식

별도 GitHub 레포(`shyoon/demo-buggy-service`)지만 **git submodule**로 demo-log-observability에 마운트한다. 이유:

- `docker compose up` 한 번으로 모든 게 빌드되도록 (Dockerfile 경로가 명확)
- AI 봇이 같은 git URL을 clone해서 worktree를 만들 때 검증 일관성
- 시연자가 `git clone --recursive <demo-log-observability>` 하면 모든 코드가 따라옴

ai-bot의 `RepoManager`는 submodule이 아니라 **별도 호스트 캐시 위치**(`/data/repos/demo-buggy-service.git`)에 bare clone을 만들어 worktree를 따로 둔다. 즉 submodule은 docker 빌드용, bare clone은 봇 분석용으로 역할 분리.

---

## 14. docker-compose.yml 확장

```yaml
services:
  # 기존: loki, grafana, alloy, loadgen (생략)

  postgres:                                          # ★ 신규
    image: postgres:16-alpine
    container_name: postgres
    environment:
      - POSTGRES_DB=buggy
      - POSTGRES_USER=buggy
      - POSTGRES_PASSWORD=buggy
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    networks: [observability-net]
    profiles: [demo]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U buggy"]
      interval: 5s

  buggy-service:                                     # ★ 신규
    build:
      context: ./demo-buggy-service
      args:
        SCENARIO: ${SCENARIO:-scenario-1}            # 시연 시 SCENARIO=scenario-4 등
    container_name: buggy-service
    ports: ["8081:8080"]
    environment:
      - SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/buggy
      - SPRING_DATASOURCE_USERNAME=buggy
      - SPRING_DATASOURCE_PASSWORD=buggy
      - SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=${HIKARI_MAX_POOL:-10}
    networks: [observability-net]
    profiles: [demo]
    depends_on:
      postgres: { condition: service_healthy }

  ai-bot:                                            # ★ 신규
    build: ./ai-bot
    container_name: ai-bot
    ports: ["8090:8090"]
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - GITHUB_REPO=${GITHUB_REPO}
      - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
      - LOKI_URL=http://loki:3100
      - WEBHOOK_TOKEN=${WEBHOOK_TOKEN}
      - DRY_RUN=${DRY_RUN:-false}
      - DAILY_COST_CAP_USD=${DAILY_COST_CAP_USD:-5}
    volumes:
      - ai_bot_data:/data           # SQLite + git bare clone 캐시
    networks: [observability-net]
    depends_on: [loki, grafana]
    profiles: [demo]
    restart: unless-stopped

volumes:
  postgres_data:                    # ★
  ai_bot_data:                      # ★
```

> `profiles: [demo]`로 묶어서 AI 봇 데모는 명시적 활성화 필요. 기존 관측성 데모(기존 demo-api)는 profile 없는 기본 서비스로 분리되어 영향 없음.

### 실행 모드

```bash
# 1) 인프라만 (기존 관측성 데모 — 변화 없음)
docker compose up -d

# 2) AI 봇 데모 풀세트 (postgres + buggy-service + ai-bot)
SCENARIO=scenario-1 docker compose --profile demo up -d --build

# 시나리오 전환
SCENARIO=scenario-4 docker compose --profile demo up -d --build buggy-service
docker compose --profile demo run --rm loadgen run /scripts/scenario-4.js

# 3) 개발 중 (인프라/DB/buggy는 컨테이너, ai-bot은 host)
docker compose --profile demo up -d postgres buggy-service loki grafana alloy
cd ai-bot && uv run uvicorn ai_bot.main:app --reload --port 8090
```

> **Grafana → ai-bot webhook URL**:
> - docker-compose 풀세트: `http://ai-bot:8090/webhooks/grafana`
> - 봇만 host 실행: `http://host.docker.internal:8090/webhooks/grafana`

---

## 15. 테스트 전략

LLM은 비결정적이라 레이어별로 전략을 분리한다.

| 레이어 | 전략 | 결정성 |
|---|---|---|
| Unit (services) | LogFetcher, RepoManager, GitHubClient, SlackNotifier, dedup, cost_guard — 외부 의존만 mock | 완전 결정적 |
| Unit (analyzer/result) | AnalysisResult Pydantic validation, 카테고리별 필수 필드 검증 | 완전 결정적 |
| Integration (LLM mock) | `FakeAgent` 어댑터로 Agent SDK wrap. 미리 정의된 `(IncidentEvent → AnalysisResult)` fixture | 완전 결정적 |
| E2E with real LLM (옵션) | 시나리오 1~6 실제 Claude API 호출. 카테고리 일치 + patch 구조(단일 파일, 30라인 이하) assertion만 | 카테고리만 결정적 |
| 시연 검증 | `docs/DEMO_GUIDE.md`의 6개 시나리오 매뉴얼 체크리스트 | 사람 |

### FakeAgent 패턴

```python
class FakeAgent:
    def __init__(self, fixtures: dict[str, AnalysisResult]):
        self._fixtures = fixtures   # key: fingerprint
    async def analyze(self, ctx: AnalysisContext) -> AnalysisResult:
        return self._fixtures[ctx.fingerprint()]

# main.py에서 DI
app.state.agent = ClaudeAgent(...) if not settings.use_fake else FakeAgent(fixtures)
```

---

## 16. 비용 견적

| 항목 | 가정 | 값 |
|---|---|---|
| 모델 | Claude Sonnet 4.6 | 입력 $3/M, 출력 $15/M |
| 분석 1건 토큰 | 입력 50K + 출력 4K | $0.21/건 |
| Agent 턴 수 | 평균 8~15 | — |
| 시연 1회 (6 시나리오) | 6건 × $0.21 | $1.26 |
| 개발 반복 | 100건/주 | $21/주 |
| 일일 cap (안전장치) | 기본값 | $5 |

라우팅 최적화(Haiku로 1차 분류 + Sonnet 심층)는 Phase 2.

---

## 17. 구현 Phase

| Phase | 범위 | 추정 |
|---|---|---|
| 1 | `demo-buggy-service` 레포 생성 (init 코드 + git-properties + MDC commit_sha + JSON 로그 + JPA + postgres 연동 + Dockerfile) | 1일 |
| 2 | 시나리오 1~3 (CODE_BUG: NPE/0나눗셈/enum) 코드 심기 + `scenario-1~3` git tag + k6 스크립트 | 0.5일 |
| 3 | demo-log-observability docker-compose 확장 (postgres + buggy-service + submodule) + Grafana alert/contactpoint 확장 + alloy buggy-service 컨테이너 인식 | 0.5일 |
| 4 | ai-bot 스켈레톤 (FastAPI + SQLite + webhook receiver + dedup + dry-run + cost_guard) | 1일 |
| 5 | LogFetcher + RepoManager (bare clone + worktree) + SlackNotifier | 0.5일 |
| 6 | Claude Agent SDK 통합 (도구 7개 + system prompt + AnalysisResult 카테고리 분류) | 1.5일 |
| 7 | GitHubClient (Issue/PR Draft 생성, DATA_ANOMALY 본문 템플릿) + Orchestrator 전체 통합 | 1일 |
| 8 | 시나리오 4 (DATA_ANOMALY: Flyway seed 깨진 row), 5 (INFRA: HikariCP 풀 + heavy endpoint), 6 (BENIGN_ERROR: streaming endpoint + k6 짧은 timeout) 코드 + tag + k6 | 1일 |
| 9 | Grafana AI 봇 대시보드, README/DEMO_GUIDE 작성, FakeAgent 기반 통합 테스트 | 1일 |
| **합계** | | **약 8일** |

---

## 18. Out of Scope (이 데모에서는 안 함)

- Kafka 메시지 브로커 (회사 기획서는 사용)
- Jira 통합 (GitHub Issue로 대체)
- Tempo trace 연동
- Prometheus/Mimir 메트릭 저장소 (기존 PROJECT.md 범위 외)
- Multi-tenant 격리
- 자동 머지 / CI 자동 실행
- 멀티모달 (이미지/스크린샷 분석)
- LLM 라우팅 (Haiku/Sonnet/Opus 분기)
- GPT-4o fallback
- 운영 DB 직접 연결 (스키마는 마이그레이션 파일에서만 읽음)
- 코드 외 자동 조치 (DB UPDATE, 인프라 설정 변경 등)

---

## 19. 알려진 한계 / 시연 시 주의사항

데모 특성상 LLM 비결정성과 자원 제약으로 다음 한계가 있다. 시연 시 미리 인지해야 한다.

1. **카테고리 분류는 비결정적** — 시나리오별 기대 카테고리는 모델 출력에 따라 다르게 나올 수 있다. 시연 전 1~2회 dry-run으로 확인하고, 결과가 일관되지 않으면 시스템 프롬프트의 분류 기준 가이드를 강화한다.
2. **시나리오 6 (BENIGN_ERROR — broken pipe)는 k6 `timeout: 50ms` 설정과 streaming endpoint(예: `/api/download/large`에서 1MB 청크 전송)가 짝을 이뤄야 안정 재현** — timeout이 너무 짧으면 connection 자체가 안 맺어지고, 너무 길면 정상 응답이 와버린다. 50~200ms 사이로 튜닝.
3. **BENIGN_ERROR 오판 위험** — 진짜 서버 측 성능 저하로 클라이언트가 끊은 경우인데 봇이 noise로 잘못 분류하면 알림이 사라지는 위험. 그래서 PR은 Draft + alert rule 자동 수정 절대 금지 + 24h 내 동일 fingerprint 반복 차단 (safety #11, #12).
4. **시나리오 5 (HikariCP 풀 고갈)는 max_pool=10 기준 동시 요청 ~30개 이상에서 발화** — k6 VU를 50 이상으로 설정해야 안정적으로 재현된다.
5. **시연 중 LLM 비용 통제** — 일일 cap 외에 시연 끝나면 `docker compose --profile demo down` 또는 ai-bot 컨테이너만 stop 권장.
6. **GitHub API rate limit** — 토큰 미인증 시 시간당 60건, 인증 시 5,000건. 데모 1회는 무관하나 반복 테스트 시 인증 토큰 필수.
7. **demo-buggy-service에 의도적 버그가 머지된 상태이므로 사용자가 main에 자동 머지 안 되게 GitHub branch protection 설정 권장** — AI가 만든 Draft PR을 실수로 머지하면 기존 버그가 사라져 시나리오 재현 불가.
8. **INSUFFICIENT_CONTEXT는 별도 시나리오 없이 자연 발현** — 시나리오 4/5에서 confidence가 0.7 미만으로 떨어지는 경우에만 보임. 시연 안정성을 위해 시스템 프롬프트의 "충분한 정보가 없을 땐 INSUFFICIENT_CONTEXT로 보고하라" 가이드를 명시적으로 넣을 것.

---

## 20. 성공 기준

이 데모가 성공했다고 판단하는 조건.

1. `docker compose --profile demo up -d` 한 줄로 모든 서비스(postgres + buggy-service + ai-bot + 기존 LGTM 스택)가 기동된다
2. 시나리오 1~3 (CODE_BUG) 실행 시 90초 내 GitHub에 코드 수정 PR이 Draft로 생성되고 Slack에 단계별 알림이 온다
3. 시나리오 4 (DATA_ANOMALY) 실행 시 PR 없이 검증 SQL/LogQL이 포함된 Issue가 생성된다
4. 시나리오 5 (INFRA_ISSUE) 실행 시 PR 없이 인프라 체크리스트가 포함된 Issue가 생성된다
5. 시나리오 6 (BENIGN_ERROR) 실행 시 `noise-reduction` 라벨이 붙은 좁은 범위 PR(ExceptionHandler 추가)과 alert rule 조정 제안 Issue가 함께 생성된다
6. `DRY_RUN=true`로 켜면 GitHub/Slack 실제 호출 없이 콘솔로 같은 결과를 볼 수 있다
7. 일일 LLM 비용 cap을 넘으면 신규 분석이 자동 거절되고 Slack 경고가 전송된다
8. 동일 fingerprint 재발화 시 새 PR/Issue 없이 기존 Issue에 댓글만 추가된다 (dedup 검증)
9. `docs/DEMO_GUIDE.md`만 보고 다른 사람이 동일 데모를 재현할 수 있다
