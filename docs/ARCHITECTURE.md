# Architecture

> 자세한 설계는 [spec](superpowers/specs/2026-06-16-ai-incident-bot-demo-design.md). 이 문서는 5분 설명용 요약.

## 한 줄 요약

Grafana Alert → ai-bot이 webhook 수신 → 배포된 commit SHA의 코드를 worktree로 마운트 → Claude Agent SDK가 도구로 코드를 탐색 → 5개 카테고리 중 하나로 분류 → 카테고리에 맞는 GitHub Issue + Draft PR 자동 생성 + Slack 알림.

## 다이어그램

```
demo-buggy-service (의도적 버그 6종)
  ↓ JSON 로그 (commit_sha MDC)
Alloy → Loki → Grafana (Alert rule)
                         ↓ Webhook (Bearer auth)
                       ai-bot (Python/FastAPI)
                         ├─ dedup (10분)
                         ├─ cost cap ($5/일)
                         ├─ LogFetcher (Loki HTTP)
                         ├─ RepoManager (git worktree at commit_sha)
                         ├─ Claude Agent SDK ─── 도구 7종
                         │                          ├─ read_file
                         │                          ├─ grep
                         │                          ├─ git_log / git_diff
                         │                          ├─ read_db_schema
                         │                          ├─ propose_patch (≤30라인)
                         │                          └─ report_finding (final)
                         ├─ GitHubClient (Issue/Draft PR)
                         └─ SlackNotifier
                              ↓
                         Slack #ai-bot-demo
```

## 5개 카테고리 → 봇 동작

| 카테고리 | 봇 동작 |
|---|---|
| CODE_BUG | Issue + Draft PR (코드 패치) |
| BENIGN_ERROR | Issue + Draft PR (ExceptionHandler) + 별도 alert rule 제안 Issue |
| DATA_ANOMALY | Issue만 (SQL + LogQL 검증 쿼리 첨부, PR 없음) |
| INFRA_ISSUE | Issue만 (점검 체크리스트) |
| INSUFFICIENT_CONTEXT | Issue만 (확인 필요 안내) |

## 안전장치 (12종 중 핵심)

- **PR은 항상 Draft** + `human-review-required` 라벨
- **confidence ≥ 0.7**만 PR 생성
- **dedup 10분 윈도우** (같은 fingerprint 무한 분석 차단)
- **BENIGN_ERROR 24시간 cooldown** (오판 시 PR 폭주 방지)
- **alert rule 자동 수정 금지** (가장 위험한 self-improving loop 차단)
- **수정 범위**: 단일 파일 + 30라인 이하
- **Allowlist 디렉토리**: `src/main/`, `src/test/`, `src/main/resources/db/migration/` 외 접근 차단
- **일일 LLM 비용 cap**: 기본 $5
- **Dry-run 모드**: GitHub/Slack 호출을 콘솔로 대체
- **Webhook Bearer 토큰** 검증

## 데모와 회사 기획서의 차이

| 항목 | 회사 기획서 | 데모 |
|---|---|---|
| 메시지 브로커 | Kafka MSK | 없음 (직접 HTTP) |
| 이슈 트래커 | Jira | GitHub Issue |
| Git 호스팅 | GitLab self-host | GitHub |
| 로그 저장소 | CloudWatch | Loki |
| LLM 통합 | anthropic SDK 직접 호출 + 직접 컨텍스트 조립 | Claude Agent SDK (자율 도구 사용) |

회사 환경 도입 시 위 항목들을 단계적으로 교체. spec 16장 참고.
