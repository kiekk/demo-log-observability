# Plan 2: AI 봇 코어 (분석 X) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ai-bot 컨테이너가 Grafana Webhook을 수신하고 → dedup → Loki에서 로그 조회 → demo-buggy-service의 worktree 생성 → Slack에 "분석 시작" 메시지까지 동작한다. LLM 호출은 아직 없고, 분석 결과는 fake stub으로 채운다. Plan 1의 `webhook-echo`를 `ai-bot`으로 교체한다.

**Architecture:** Python 3.12 + FastAPI + SQLAlchemy(async) + SQLite. `Orchestrator`가 webhook 수신부터 Slack 알림까지 단일 파이프라인을 조립. LLM 호출이 들어갈 자리는 `FakeAnalyzer`로 stub (Plan 3에서 진짜 Claude Agent SDK로 교체). 모든 외부 호출(Slack/Git/Loki)은 `services/` 디렉토리에 격리. 안전장치(dedup, dry-run, cost_guard)는 `safety/` 디렉토리에 격리.

**Tech Stack:**
- Python 3.12
- uv (의존성/실행)
- FastAPI 0.115 + uvicorn
- Pydantic v2 + pydantic-settings
- SQLAlchemy 2.0 (async) + aiosqlite + Alembic
- httpx (Loki client)
- GitPython 3.1 (bare clone + worktree)
- slack-sdk 3.31
- pytest 8 + pytest-asyncio + httpx (test client) + respx (HTTP mock)

**관련 문서:**
- spec: `docs/superpowers/specs/2026-06-16-ai-incident-bot-demo-design.md` (Phase 4~5)
- 이전 plan: `docs/superpowers/plans/2026-06-16-plan-1-base-infra-buggy-service.md` 완료 가정

---

## 사전 작업

- [ ] **A. Plan 1 완료 확인**
  - `docker compose --profile demo up -d`로 postgres + buggy-service + LGTM + webhook-echo 기동 동작
  - 시나리오 1~3 k6 트리거 시 webhook-echo 컨테이너 로그에 Grafana payload 도달 확인

- [ ] **B. uv 설치 확인**

Run:
```bash
which uv || curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
```

Expected: `uv 0.5.x` 또는 그 이상

- [ ] **C. Slack Incoming Webhook URL 발급 (Task 11에서 사용)**
  - api.slack.com/apps → 새 앱 생성 → Incoming Webhooks 활성화 → 채널 선택
  - URL `.env`에 `SLACK_WEBHOOK_URL=...` 추가 (Claude한테 값 알려주지 말 것)

- [ ] **D. `.env`에 추가 환경변수 설정**

`~/Documents/study/demo-log-observability/demo-log-observability/.env`에 다음이 있는지 확인 (없으면 `nano .env`로 직접 추가):

```bash
ANTHROPIC_API_KEY=sk-ant-...        # Plan 3에서 사용, Plan 2에서는 불필요
GITHUB_TOKEN=ghp_...                 # Plan 3, 불필요
GITHUB_REPO=kiekk/demo-buggy-service
GITHUB_REPO_URL=https://github.com/kiekk/demo-buggy-service.git
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
WEBHOOK_TOKEN=...                    # openssl rand -hex 16
AI_BOT_WEBHOOK_URL=http://ai-bot:8090/webhooks/grafana
HIKARI_MAX_POOL=10
DRY_RUN=false
DAILY_COST_CAP_USD=5
```

---

## File Structure

`$REPO`는 `~/Documents/study/demo-log-observability/demo-log-observability/`.

```
$REPO/
├── ai-bot/                                    ★ 신규 (Plan 2)
│   ├── pyproject.toml                         (Task 1)
│   ├── uv.lock                                (Task 1 자동 생성)
│   ├── Dockerfile                             (Task 14)
│   ├── README.md                              (Task 14)
│   ├── alembic.ini                            (Task 4)
│   ├── src/ai_bot/
│   │   ├── __init__.py                        (Task 1)
│   │   ├── main.py                            (Task 13)
│   │   ├── config.py                          (Task 2)
│   │   ├── webhook/
│   │   │   ├── __init__.py
│   │   │   ├── receiver.py                    (Task 6)
│   │   │   └── schemas.py                     (Task 5)
│   │   ├── orchestrator.py                    (Task 12)
│   │   ├── analyzer/
│   │   │   ├── __init__.py
│   │   │   ├── result.py                      (Task 12 — AnalysisResult Pydantic)
│   │   │   └── fake.py                        (Task 12 — Plan 3에서 real로 교체)
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── log_fetcher.py                 (Task 9)
│   │   │   ├── repo_manager.py                (Task 10)
│   │   │   └── slack_notifier.py              (Task 11)
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                      (Task 3)
│   │   │   ├── session.py                     (Task 3)
│   │   │   └── migrations/                    (Task 4 — alembic)
│   │   │       ├── env.py
│   │   │       ├── script.py.mako
│   │   │       └── versions/
│   │   └── safety/
│   │       ├── __init__.py
│   │       ├── dedup.py                       (Task 7)
│   │       └── cost_guard.py                  (Task 8)
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py                        (Task 3)
│       ├── unit/
│       │   ├── test_config.py                 (Task 2)
│       │   ├── test_dedup.py                  (Task 7)
│       │   ├── test_cost_guard.py             (Task 8)
│       │   ├── test_log_fetcher.py            (Task 9)
│       │   ├── test_repo_manager.py           (Task 10)
│       │   └── test_slack_notifier.py         (Task 11)
│       └── integration/
│           ├── test_webhook_receiver.py       (Task 6)
│           └── test_orchestrator.py           (Task 12)
└── docker-compose.yml                         (Task 14 수정 — webhook-echo 제거, ai-bot 추가)
```

---

## Task 1: ai-bot Python 프로젝트 셋업 (uv + pyproject.toml)

**Files:**
- Create: `$REPO/ai-bot/pyproject.toml`
- Create: `$REPO/ai-bot/src/ai_bot/__init__.py`
- Create: `$REPO/ai-bot/.python-version`

- [ ] **Step 1: 디렉토리 구조 생성**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
mkdir -p ai-bot/src/ai_bot/{webhook,analyzer,services,db/migrations/versions,safety}
mkdir -p ai-bot/tests/{unit,integration}
touch ai-bot/src/ai_bot/__init__.py
touch ai-bot/src/ai_bot/{webhook,analyzer,services,db,safety}/__init__.py
touch ai-bot/tests/__init__.py
touch ai-bot/tests/{unit,integration}/__init__.py
```

- [ ] **Step 2: .python-version**

Create `ai-bot/.python-version`:
```
3.12
```

- [ ] **Step 3: pyproject.toml**

Create `ai-bot/pyproject.toml`:

```toml
[project]
name = "ai-bot"
version = "0.1.0"
description = "AI Incident Bot - analyzes errors and proposes fixes via Claude Agent SDK"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "aiosqlite>=0.20.0",
    "alembic>=1.14.0",
    "httpx>=0.27.2",
    "gitpython>=3.1.43",
    "slack-sdk>=3.31.0",
    "python-multipart>=0.0.12",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "respx>=0.21.1",
    "pytest-mock>=3.14.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ai_bot"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]

[tool.uv]
package = true
```

- [ ] **Step 4: uv로 의존성 설치 검증**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability/ai-bot
uv sync
ls .venv/bin/uvicorn .venv/bin/alembic .venv/bin/pytest
```

Expected: 세 파일 모두 존재

- [ ] **Step 5: 기본 import smoke test**

Run:
```bash
uv run python -c "import fastapi, sqlalchemy, httpx, git, slack_sdk; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
echo ".venv/" >> ai-bot/.gitignore
echo "__pycache__/" >> ai-bot/.gitignore
echo "*.pyc" >> ai-bot/.gitignore
echo ".pytest_cache/" >> ai-bot/.gitignore
echo "*.db" >> ai-bot/.gitignore
git add ai-bot/pyproject.toml ai-bot/uv.lock ai-bot/.python-version ai-bot/.gitignore \
        ai-bot/src/ ai-bot/tests/
git commit -m "feat(ai-bot): scaffold Python project with uv (FastAPI/SQLAlchemy/GitPython/slack-sdk)"
```

---

## Task 2: Config (pydantic-settings)

**Files:**
- Create: `ai-bot/src/ai_bot/config.py`
- Create: `ai-bot/tests/unit/test_config.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_config.py`:

```python
import os

import pytest

from ai_bot.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_TOKEN", "test-token-123")
    monkeypatch.setenv("LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/owner/repo.git")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X")
    monkeypatch.setenv("DB_PATH", "/tmp/test.db")

    settings = Settings()  # type: ignore[call-arg]
    assert settings.webhook_token == "test-token-123"
    assert settings.loki_url == "http://loki:3100"
    assert settings.dry_run is False  # default
    assert settings.daily_cost_cap_usd == 5.0  # default
    assert settings.dedup_window_minutes == 10  # default
    assert settings.max_concurrent_analyses == 2  # default


def test_settings_dry_run_truthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("LOKI_URL", "x")
    monkeypatch.setenv("GITHUB_REPO", "x")
    monkeypatch.setenv("GITHUB_REPO_URL", "x")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "x")
    monkeypatch.setenv("DB_PATH", "x")
    monkeypatch.setenv("DRY_RUN", "true")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.dry_run is True
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_config.py -v
```

Expected: FAIL — `ImportError: cannot import name 'Settings'`

- [ ] **Step 3: Settings 구현**

Create `ai-bot/src/ai_bot/config.py`:

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required
    webhook_token: str = Field(alias="WEBHOOK_TOKEN")
    loki_url: str = Field(alias="LOKI_URL")
    github_repo: str = Field(alias="GITHUB_REPO")
    github_repo_url: str = Field(alias="GITHUB_REPO_URL")
    slack_webhook_url: str = Field(alias="SLACK_WEBHOOK_URL")
    db_path: str = Field(alias="DB_PATH")

    # Optional with defaults
    dry_run: bool = Field(default=False, alias="DRY_RUN")
    daily_cost_cap_usd: float = Field(default=5.0, alias="DAILY_COST_CAP_USD")
    dedup_window_minutes: int = Field(default=10, alias="DEDUP_WINDOW_MINUTES")
    max_concurrent_analyses: int = Field(default=2, alias="MAX_CONCURRENT_ANALYSES")
    bot_port: int = Field(default=8090, alias="BOT_PORT")
    repo_cache_dir: str = Field(default="/data/repos", alias="REPO_CACHE_DIR")
    worktree_dir: str = Field(default="/data/worktrees", alias="WORKTREE_DIR")
    log_query_window_minutes: int = Field(default=10, alias="LOG_QUERY_WINDOW_MINUTES")
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_config.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/config.py ai-bot/tests/unit/test_config.py
git commit -m "feat(config): Settings via pydantic-settings with env var aliases"
```

---

## Task 3: SQLite DB 모델 + Session

**Files:**
- Create: `ai-bot/src/ai_bot/db/models.py`
- Create: `ai-bot/src/ai_bot/db/session.py`
- Create: `ai-bot/tests/conftest.py`

- [ ] **Step 1: conftest.py 작성 (테스트용 in-memory DB fixture)**

Create `ai-bot/tests/conftest.py`:

```python
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_bot.db.models import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def fixed_now():
    """Plan 7에서 시간 의존 테스트 만들 때 쓸 헬퍼. 일단 빈 fixture."""
    from datetime import datetime, UTC
    return datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
```

- [ ] **Step 2: 실패하는 모델 테스트 작성**

Create `ai-bot/tests/unit/test_models.py`:

```python
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import AnalysisRun, Incident, LlmUsage


@pytest.mark.asyncio
async def test_incident_insert_and_query(db_session: AsyncSession) -> None:
    incident = Incident(
        fingerprint="fp-test-1",
        service="demo-buggy-service",
        commit_sha="abc123",
        error_class="NullPointerException",
        request_id="r-1",
        occurrence_count=1,
    )
    db_session.add(incident)
    await db_session.commit()

    result = await db_session.execute(select(Incident).where(Incident.fingerprint == "fp-test-1"))
    fetched = result.scalar_one()
    assert fetched.service == "demo-buggy-service"
    assert fetched.commit_sha == "abc123"


@pytest.mark.asyncio
async def test_analysis_run_with_incident(db_session: AsyncSession) -> None:
    incident = Incident(
        fingerprint="fp-test-2",
        service="demo-buggy-service",
        commit_sha="def456",
        error_class="ArithmeticException",
        request_id="r-2",
        occurrence_count=1,
    )
    db_session.add(incident)
    await db_session.flush()

    run = AnalysisRun(
        incident_id=incident.id,
        status="PENDING",
        started_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()

    result = await db_session.execute(select(AnalysisRun).where(AnalysisRun.incident_id == incident.id))
    fetched = result.scalar_one()
    assert fetched.status == "PENDING"


@pytest.mark.asyncio
async def test_llm_usage(db_session: AsyncSession) -> None:
    incident = Incident(
        fingerprint="fp-test-3",
        service="demo-buggy-service",
        commit_sha="ghi789",
        error_class="X",
        request_id="r-3",
        occurrence_count=1,
    )
    db_session.add(incident)
    await db_session.flush()
    run = AnalysisRun(incident_id=incident.id, status="COMPLETED", started_at=datetime.now(UTC))
    db_session.add(run)
    await db_session.flush()
    usage = LlmUsage(
        run_id=run.id,
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.01,
        tool_calls_count=5,
        latency_ms=12345,
    )
    db_session.add(usage)
    await db_session.commit()

    result = await db_session.execute(select(LlmUsage).where(LlmUsage.run_id == run.id))
    fetched = result.scalar_one()
    assert fetched.cost_usd == 0.01
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_models.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 4: SQLAlchemy 모델 작성**

Create `ai-bot/src/ai_bot/db/models.py`:

```python
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


RunStatus = Literal["PENDING", "ANALYZING", "CREATING_PR", "COMPLETED", "FAILED", "REJECTED"]


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_incidents_fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    service: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    error_class: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    github_issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(String, nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="runs")
    usages: Mapped[list["LlmUsage"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tool_calls_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False
    )

    run: Mapped["AnalysisRun"] = relationship(back_populates="usages")
```

- [ ] **Step 5: session.py 작성**

Create `ai-bot/src/ai_bot/db/session.py`:

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_engine(db_path: str) -> AsyncEngine:
    url = f"sqlite+aiosqlite:///{db_path}"
    return create_async_engine(url, future=True, echo=False)


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(session_maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        yield session
```

- [ ] **Step 6: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_models.py tests/unit/test_config.py -v
```

Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/db/ ai-bot/tests/conftest.py ai-bot/tests/unit/test_models.py
git commit -m "feat(db): SQLAlchemy models (Incident/AnalysisRun/LlmUsage) + async session"
```

---

## Task 4: Alembic 마이그레이션 초기 설정

**Files:**
- Create: `ai-bot/alembic.ini`
- Create: `ai-bot/src/ai_bot/db/migrations/env.py`
- Create: `ai-bot/src/ai_bot/db/migrations/script.py.mako`
- Create: `ai-bot/src/ai_bot/db/migrations/versions/0001_initial.py`

- [ ] **Step 1: alembic init**

Run:
```bash
cd ai-bot
uv run alembic init -t async src/ai_bot/db/migrations
```

Expected: `src/ai_bot/db/migrations/` 안에 `env.py`, `script.py.mako`, `versions/` 디렉토리 생성. `alembic.ini` 루트에 생성.

- [ ] **Step 2: alembic.ini 경로 수정**

`alembic.ini`에서 `script_location` 라인을 다음으로 변경:

```ini
script_location = src/ai_bot/db/migrations
```

`sqlalchemy.url` 라인을 빈 값으로 (env.py에서 동적 주입):

```ini
sqlalchemy.url =
```

- [ ] **Step 3: env.py 수정 — Settings에서 DB 경로 가져오기**

`src/ai_bot/db/migrations/env.py`를 다음으로 교체:

```python
import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

from ai_bot.config import Settings
from ai_bot.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    settings = Settings()  # type: ignore[call-arg]
    return f"sqlite+aiosqlite:///{settings.db_path}"


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(_get_url(), future=True)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: 초기 revision 생성**

Run:
```bash
cd ai-bot
# 임시 env로 alembic이 db_path를 가져올 수 있게
WEBHOOK_TOKEN=x LOKI_URL=x GITHUB_REPO=x GITHUB_REPO_URL=x \
SLACK_WEBHOOK_URL=x DB_PATH=/tmp/ai-bot-dev.db \
uv run alembic revision --autogenerate -m "initial"
```

Expected: `src/ai_bot/db/migrations/versions/<hash>_initial.py` 생성. 안에 `incidents`, `analysis_runs`, `llm_usage` 테이블 create.

- [ ] **Step 5: 생성된 revision 파일명을 0001_initial.py로 변경 (정렬용)**

Run:
```bash
cd ai-bot
mv src/ai_bot/db/migrations/versions/*_initial.py src/ai_bot/db/migrations/versions/0001_initial.py
head -5 src/ai_bot/db/migrations/versions/0001_initial.py
```

Expected: revision id가 자동 생성된 hash. (rename은 파일명만 변경, 내용 영향 없음)

- [ ] **Step 6: 마이그레이션 실행 검증 (실제 DB 파일에)**

Run:
```bash
cd ai-bot
rm -f /tmp/ai-bot-dev.db
WEBHOOK_TOKEN=x LOKI_URL=x GITHUB_REPO=x GITHUB_REPO_URL=x \
SLACK_WEBHOOK_URL=x DB_PATH=/tmp/ai-bot-dev.db \
uv run alembic upgrade head

sqlite3 /tmp/ai-bot-dev.db ".tables"
```

Expected: `alembic_version  analysis_runs  incidents  llm_usage`

- [ ] **Step 7: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/alembic.ini ai-bot/src/ai_bot/db/migrations/
git commit -m "feat(db): alembic async migration setup with initial revision"
```

---

## Task 5: Grafana Webhook Payload Pydantic 스키마

**Files:**
- Create: `ai-bot/src/ai_bot/webhook/schemas.py`
- Create: `ai-bot/tests/unit/test_webhook_schemas.py`

Grafana Webhook payload 구조 (Grafana 10.2 기준):
```json
{
  "receiver": "ai-bot-webhook",
  "status": "firing",
  "alerts": [{
    "status": "firing",
    "labels": {"alertname": "...", "service": "...", "commit_sha": "..."},
    "annotations": {...},
    "startsAt": "...",
    "values": {...}
  }],
  "commonLabels": {"service": "demo-buggy-service", "commit_sha": "abc123"},
  "groupLabels": {...},
  "externalURL": "...",
  "version": "1"
}
```

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_webhook_schemas.py`:

```python
from ai_bot.webhook.schemas import GrafanaWebhookPayload, IncidentEvent


def test_parse_minimal_grafana_payload() -> None:
    raw = {
        "receiver": "ai-bot-webhook",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "AI Bot - Buggy Service Error",
                    "service": "demo-buggy-service",
                    "commit_sha": "abc123",
                },
                "annotations": {},
                "startsAt": "2026-06-17T12:00:00Z",
            }
        ],
        "commonLabels": {
            "service": "demo-buggy-service",
            "commit_sha": "abc123",
        },
        "groupLabels": {"alertname": "AI Bot - Buggy Service Error"},
    }
    payload = GrafanaWebhookPayload.model_validate(raw)
    assert payload.status == "firing"
    assert payload.commonLabels["service"] == "demo-buggy-service"
    assert payload.commonLabels["commit_sha"] == "abc123"
    assert len(payload.alerts) == 1


def test_to_incident_event() -> None:
    raw = {
        "receiver": "ai-bot-webhook",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"service": "demo-buggy-service", "commit_sha": "abc123"},
                "annotations": {},
                "startsAt": "2026-06-17T12:00:00Z",
            }
        ],
        "commonLabels": {"service": "demo-buggy-service", "commit_sha": "abc123"},
        "groupLabels": {},
    }
    payload = GrafanaWebhookPayload.model_validate(raw)
    event = IncidentEvent.from_grafana(payload)
    assert event.service == "demo-buggy-service"
    assert event.commit_sha == "abc123"


def test_resolved_status_returns_empty_events() -> None:
    raw = {
        "receiver": "ai-bot-webhook",
        "status": "resolved",
        "alerts": [],
        "commonLabels": {},
        "groupLabels": {},
    }
    payload = GrafanaWebhookPayload.model_validate(raw)
    # resolved 상태에서는 봇이 무시 — IncidentEvent를 만들지 않음
    assert payload.status == "resolved"
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_webhook_schemas.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: 스키마 구현**

Create `ai-bot/src/ai_bot/webhook/schemas.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GrafanaAlert(BaseModel):
    status: str
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime | None = None


class GrafanaWebhookPayload(BaseModel):
    receiver: str = ""
    status: Literal["firing", "resolved"] = "firing"
    alerts: list[GrafanaAlert] = Field(default_factory=list)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    groupLabels: dict[str, str] = Field(default_factory=dict)
    externalURL: str = ""
    version: str = ""


class IncidentEvent(BaseModel):
    """봇 내부에서 쓰는 정규화된 incident 표현."""

    service: str
    commit_sha: str
    error_class: str = "Unknown"
    request_id: str | None = None
    grafana_alert_url: str | None = None

    @classmethod
    def from_grafana(cls, payload: GrafanaWebhookPayload) -> IncidentEvent:
        labels = payload.commonLabels or {}
        # commonLabels에 없으면 첫 alert의 labels로 fallback
        if not labels and payload.alerts:
            labels = payload.alerts[0].labels

        return cls(
            service=labels.get("service", "unknown"),
            commit_sha=labels.get("commit_sha", "unknown"),
            error_class=labels.get("error_class", "Unknown"),
            request_id=labels.get("request_id"),
            grafana_alert_url=payload.externalURL or None,
        )
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_webhook_schemas.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/webhook/schemas.py ai-bot/tests/unit/test_webhook_schemas.py
git commit -m "feat(webhook): Pydantic schemas for Grafana payload + IncidentEvent normalization"
```

---

## Task 6: Webhook Receiver (FastAPI) + Bearer 토큰 검증

**Files:**
- Create: `ai-bot/src/ai_bot/webhook/receiver.py`
- Create: `ai-bot/tests/integration/test_webhook_receiver.py`

- [ ] **Step 1: 통합 테스트 작성**

Create `ai-bot/tests/integration/test_webhook_receiver.py`:

```python
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_bot.config import Settings
from ai_bot.webhook.receiver import build_router


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    monkeypatch.setenv("WEBHOOK_TOKEN", "secret-token-123")
    monkeypatch.setenv("LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/owner/repo.git")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    return Settings()  # type: ignore[call-arg]


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    received: list[dict] = []

    async def handler(event: dict) -> None:
        received.append(event)

    app = FastAPI()
    app.include_router(build_router(settings=settings, on_incident=handler))
    app.state.received = received
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _valid_payload() -> dict:
    return {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"service": "demo-buggy-service", "commit_sha": "abc123"},
                "annotations": {},
                "startsAt": "2026-06-17T12:00:00Z",
            }
        ],
        "commonLabels": {"service": "demo-buggy-service", "commit_sha": "abc123"},
        "groupLabels": {},
    }


def test_missing_authorization_returns_401(client: TestClient) -> None:
    r = client.post("/webhooks/grafana", json=_valid_payload())
    assert r.status_code == 401


def test_wrong_token_returns_401(client: TestClient) -> None:
    r = client.post(
        "/webhooks/grafana",
        json=_valid_payload(),
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


def test_valid_request_returns_202_and_triggers_handler(client: TestClient, app: FastAPI) -> None:
    r = client.post(
        "/webhooks/grafana",
        json=_valid_payload(),
        headers={"Authorization": "Bearer secret-token-123"},
    )
    assert r.status_code == 202
    assert len(app.state.received) == 1
    assert app.state.received[0].service == "demo-buggy-service"


def test_resolved_status_returns_204_without_handler_call(client: TestClient, app: FastAPI) -> None:
    payload = _valid_payload()
    payload["status"] = "resolved"
    r = client.post(
        "/webhooks/grafana",
        json=payload,
        headers={"Authorization": "Bearer secret-token-123"},
    )
    assert r.status_code == 204
    assert len(app.state.received) == 0
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/integration/test_webhook_receiver.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Receiver 구현**

Create `ai-bot/src/ai_bot/webhook/receiver.py`:

```python
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

from ai_bot.config import Settings
from ai_bot.webhook.schemas import GrafanaWebhookPayload, IncidentEvent

IncidentHandler = Callable[[IncidentEvent], Awaitable[None]]


def build_router(
    *,
    settings: Settings,
    on_incident: IncidentHandler,
) -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/grafana")
    async def receive_grafana_webhook(
        payload: GrafanaWebhookPayload,
        background: BackgroundTasks,
        authorization: str | None = Header(default=None),
    ):
        _verify_token(authorization, settings.webhook_token)

        if payload.status == "resolved":
            return _no_content()

        event = IncidentEvent.from_grafana(payload)
        background.add_task(on_incident, event)
        return _accepted({"service": event.service, "commit_sha": event.commit_sha})

    return router


def _verify_token(authorization: str | None, expected: str) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def _accepted(body: dict) -> "object":
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body)


def _no_content() -> "object":
    from fastapi.responses import Response

    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/integration/test_webhook_receiver.py -v
```

Expected: PASS (4 tests). 단 `BackgroundTasks`는 동기로 실행되지 않고 response 후 실행되는데 TestClient는 background도 응답 완료 후 실행. 따라서 assertion이 정상 동작.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/webhook/receiver.py ai-bot/tests/integration/test_webhook_receiver.py
git commit -m "feat(webhook): Grafana webhook receiver with bearer auth + background dispatch"
```

---

## Task 7: Dedup (fingerprint + 10분 윈도우)

**Files:**
- Create: `ai-bot/src/ai_bot/safety/dedup.py`
- Create: `ai-bot/tests/unit/test_dedup.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_dedup.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import Incident
from ai_bot.safety.dedup import DedupResult, compute_fingerprint, dedup_or_register
from ai_bot.webhook.schemas import IncidentEvent


def _event(service: str = "demo-buggy-service", sha: str = "abc123", err: str = "NPE") -> IncidentEvent:
    return IncidentEvent(service=service, commit_sha=sha, error_class=err, request_id="r-1")


def test_compute_fingerprint_is_deterministic() -> None:
    e1 = _event()
    e2 = _event()
    assert compute_fingerprint(e1) == compute_fingerprint(e2)


def test_compute_fingerprint_differs_by_field() -> None:
    assert compute_fingerprint(_event(sha="abc")) != compute_fingerprint(_event(sha="def"))
    assert compute_fingerprint(_event(err="NPE")) != compute_fingerprint(_event(err="OOM"))


@pytest.mark.asyncio
async def test_first_occurrence_returns_NEW(db_session: AsyncSession) -> None:
    event = _event()
    result = await dedup_or_register(db_session, event, window_minutes=10, now=datetime.now(UTC))
    assert result.kind == "NEW"
    assert result.incident_id is not None
    assert result.occurrence_count == 1


@pytest.mark.asyncio
async def test_second_occurrence_within_window_returns_DUPLICATE(db_session: AsyncSession) -> None:
    event = _event()
    t0 = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    first = await dedup_or_register(db_session, event, window_minutes=10, now=t0)
    second = await dedup_or_register(db_session, event, window_minutes=10, now=t0 + timedelta(minutes=5))
    assert first.kind == "NEW"
    assert second.kind == "DUPLICATE"
    assert second.incident_id == first.incident_id
    assert second.occurrence_count == 2


@pytest.mark.asyncio
async def test_occurrence_outside_window_returns_NEW(db_session: AsyncSession) -> None:
    event = _event()
    t0 = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    first = await dedup_or_register(db_session, event, window_minutes=10, now=t0)
    second = await dedup_or_register(db_session, event, window_minutes=10, now=t0 + timedelta(minutes=11))
    # 같은 fingerprint이지만 윈도우 밖이라 NEW로 취급 — 같은 incident row의 occurrence_count만 증가
    # (Spec: 같은 incident에 댓글만 추가하는 게 아니라, 윈도우 밖이면 새 분석 진행 가능)
    # 구현 결정: 같은 fingerprint 윈도우 밖이면 EXPIRED — 호출자는 새 분석으로 처리
    assert second.kind == "EXPIRED"
    assert second.incident_id == first.incident_id
    assert second.occurrence_count == 2
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_dedup.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Dedup 구현**

Create `ai-bot/src/ai_bot/safety/dedup.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import Incident
from ai_bot.webhook.schemas import IncidentEvent


@dataclass
class DedupResult:
    kind: Literal["NEW", "DUPLICATE", "EXPIRED"]
    incident_id: int
    occurrence_count: int


def compute_fingerprint(event: IncidentEvent) -> str:
    raw = f"{event.service}|{event.commit_sha}|{event.error_class}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def dedup_or_register(
    session: AsyncSession,
    event: IncidentEvent,
    *,
    window_minutes: int,
    now: datetime,
) -> DedupResult:
    fp = compute_fingerprint(event)
    result = await session.execute(select(Incident).where(Incident.fingerprint == fp))
    existing = result.scalar_one_or_none()

    if existing is None:
        incident = Incident(
            fingerprint=fp,
            service=event.service,
            commit_sha=event.commit_sha,
            error_class=event.error_class,
            request_id=event.request_id,
            first_seen=now,
            last_seen=now,
            occurrence_count=1,
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)
        return DedupResult(kind="NEW", incident_id=incident.id, occurrence_count=1)

    # 기존 fingerprint 존재 → 윈도우 안인지 확인
    existing_last = existing.last_seen
    if existing_last.tzinfo is None:
        # SQLite는 timezone-naive로 저장될 수 있음
        from datetime import UTC
        existing_last = existing_last.replace(tzinfo=UTC)
    within_window = (now - existing_last) <= timedelta(minutes=window_minutes)

    existing.occurrence_count += 1
    existing.last_seen = now
    await session.commit()
    await session.refresh(existing)

    kind: Literal["DUPLICATE", "EXPIRED"] = "DUPLICATE" if within_window else "EXPIRED"
    return DedupResult(kind=kind, incident_id=existing.id, occurrence_count=existing.occurrence_count)
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_dedup.py -v
```

Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/safety/dedup.py ai-bot/tests/unit/test_dedup.py
git commit -m "feat(safety): dedup via fingerprint (service|commit_sha|error_class) + window check"
```

---

## Task 8: Cost Guard (daily cap)

**Files:**
- Create: `ai-bot/src/ai_bot/safety/cost_guard.py`
- Create: `ai-bot/tests/unit/test_cost_guard.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_cost_guard.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import AnalysisRun, Incident, LlmUsage
from ai_bot.safety.cost_guard import check_daily_cap, record_usage


@pytest.mark.asyncio
async def test_check_daily_cap_under_limit_passes(db_session: AsyncSession) -> None:
    allowed = await check_daily_cap(db_session, cap_usd=5.0, now=datetime.now(UTC))
    assert allowed is True


@pytest.mark.asyncio
async def test_check_daily_cap_over_limit_blocks(db_session: AsyncSession) -> None:
    t0 = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    # 셋업: incident + run + usage 6달러
    incident = Incident(fingerprint="fp", service="s", commit_sha="c", error_class="E", request_id="r", occurrence_count=1)
    db_session.add(incident)
    await db_session.flush()
    run = AnalysisRun(incident_id=incident.id, status="COMPLETED", started_at=t0)
    db_session.add(run)
    await db_session.flush()
    db_session.add(LlmUsage(run_id=run.id, model="x", input_tokens=0, output_tokens=0, cost_usd=6.0, tool_calls_count=0, latency_ms=0))
    await db_session.commit()

    allowed = await check_daily_cap(db_session, cap_usd=5.0, now=t0 + timedelta(hours=1))
    assert allowed is False


@pytest.mark.asyncio
async def test_check_daily_cap_yesterday_usage_does_not_count(db_session: AsyncSession) -> None:
    today = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    yesterday = today - timedelta(days=1)

    incident = Incident(fingerprint="fp", service="s", commit_sha="c", error_class="E", request_id="r", occurrence_count=1)
    db_session.add(incident)
    await db_session.flush()
    run = AnalysisRun(incident_id=incident.id, status="COMPLETED", started_at=yesterday)
    db_session.add(run)
    await db_session.flush()
    # 어제 사용량 100달러 — 오늘은 무관
    db_session.add(LlmUsage(run_id=run.id, model="x", input_tokens=0, output_tokens=0, cost_usd=100.0, tool_calls_count=0, latency_ms=0))
    await db_session.commit()

    allowed = await check_daily_cap(db_session, cap_usd=5.0, now=today)
    assert allowed is True


@pytest.mark.asyncio
async def test_record_usage_persists(db_session: AsyncSession) -> None:
    incident = Incident(fingerprint="fp", service="s", commit_sha="c", error_class="E", request_id="r", occurrence_count=1)
    db_session.add(incident)
    await db_session.flush()
    run = AnalysisRun(incident_id=incident.id, status="COMPLETED", started_at=datetime.now(UTC))
    db_session.add(run)
    await db_session.flush()

    await record_usage(
        db_session, run_id=run.id, model="claude-sonnet-4-6",
        input_tokens=1000, output_tokens=500, cost_usd=0.05, tool_calls_count=3, latency_ms=12000,
    )
    from sqlalchemy import select
    res = await db_session.execute(select(LlmUsage).where(LlmUsage.run_id == run.id))
    fetched = res.scalar_one()
    assert fetched.cost_usd == 0.05
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_cost_guard.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Cost guard 구현**

Create `ai-bot/src/ai_bot/safety/cost_guard.py`:

```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import LlmUsage


async def check_daily_cap(session: AsyncSession, *, cap_usd: float, now: datetime) -> bool:
    """오늘(UTC) 누적 비용이 cap 미만이면 True 반환."""
    start_of_today = datetime(now.year, now.month, now.day, tzinfo=UTC)
    end_of_today = start_of_today + timedelta(days=1)
    stmt = select(func.coalesce(func.sum(LlmUsage.cost_usd), 0.0)).where(
        LlmUsage.created_at >= start_of_today,
        LlmUsage.created_at < end_of_today,
    )
    total = (await session.execute(stmt)).scalar_one()
    return float(total) < cap_usd


async def record_usage(
    session: AsyncSession,
    *,
    run_id: int,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    tool_calls_count: int,
    latency_ms: int,
) -> None:
    usage = LlmUsage(
        run_id=run_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        tool_calls_count=tool_calls_count,
        latency_ms=latency_ms,
    )
    session.add(usage)
    await session.commit()
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_cost_guard.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/safety/cost_guard.py ai-bot/tests/unit/test_cost_guard.py
git commit -m "feat(safety): daily LLM cost cap check + usage recording"
```

---

## Task 9: LogFetcher (Loki HTTP client)

**Files:**
- Create: `ai-bot/src/ai_bot/services/log_fetcher.py`
- Create: `ai-bot/tests/unit/test_log_fetcher.py`

LogFetcher는 webhook의 commit_sha + (선택)request_id로 Loki에서 관련 에러 로그를 가져온다.

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_log_fetcher.py`:

```python
import pytest
import respx
from httpx import Response

from ai_bot.services.log_fetcher import LogFetcher, LogLine


@pytest.mark.asyncio
@respx.mock
async def test_fetch_by_commit_sha_returns_log_lines() -> None:
    sample_response = {
        "data": {
            "resultType": "streams",
            "result": [
                {
                    "stream": {"service": "demo-buggy-service", "level": "ERROR"},
                    "values": [
                        ["1718600000000000000", '{"timestamp":"2026-06-17T12:00:00Z","message":"NPE here","level":"ERROR","exception_class":"NullPointerException","request_id":"r-1"}'],
                        ["1718600001000000000", '{"timestamp":"2026-06-17T12:00:01Z","message":"another error","level":"ERROR","exception_class":"NullPointerException","request_id":"r-2"}'],
                    ],
                }
            ],
        }
    }
    respx.get("http://loki:3100/loki/api/v1/query_range").mock(return_value=Response(200, json=sample_response))

    fetcher = LogFetcher(loki_url="http://loki:3100")
    lines = await fetcher.fetch_recent_errors(service="demo-buggy-service", commit_sha="abc123", window_minutes=10)

    assert len(lines) == 2
    assert all(isinstance(line, LogLine) for line in lines)
    assert lines[0].exception_class == "NullPointerException"
    assert lines[0].request_id == "r-1"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_empty_on_no_results() -> None:
    respx.get("http://loki:3100/loki/api/v1/query_range").mock(
        return_value=Response(200, json={"data": {"result": []}})
    )
    fetcher = LogFetcher(loki_url="http://loki:3100")
    lines = await fetcher.fetch_recent_errors(service="x", commit_sha="y", window_minutes=10)
    assert lines == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_handles_loki_error() -> None:
    respx.get("http://loki:3100/loki/api/v1/query_range").mock(return_value=Response(500))
    fetcher = LogFetcher(loki_url="http://loki:3100")
    # spec: Loki 실패 시 빈 리스트 반환 (fallback) — 호출자는 컨텍스트 없이 분석 진행
    lines = await fetcher.fetch_recent_errors(service="x", commit_sha="y", window_minutes=10)
    assert lines == []
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_log_fetcher.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: LogFetcher 구현**

Create `ai-bot/src/ai_bot/services/log_fetcher.py`:

```python
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LogLine:
    timestamp_ns: int
    message: str
    level: str
    exception_class: str | None
    request_id: str | None
    raw: dict


class LogFetcher:
    def __init__(self, loki_url: str, timeout_seconds: float = 10.0) -> None:
        self._loki_url = loki_url.rstrip("/")
        self._timeout = timeout_seconds

    async def fetch_recent_errors(
        self, *, service: str, commit_sha: str, window_minutes: int, limit: int = 50,
    ) -> list[LogLine]:
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - window_minutes * 60 * 1_000_000_000
        query = (
            f'{{service="{service}"}} | json '
            f'| commit_sha="{commit_sha}" | level="ERROR"'
        )
        params = {
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": str(limit),
            "direction": "backward",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._loki_url}/loki/api/v1/query_range", params=params)
            if resp.status_code != 200:
                logger.warning("Loki returned %s — falling back to empty log context", resp.status_code)
                return []
            data = resp.json().get("data", {})
            return _parse_streams(data.get("result", []))
        except (httpx.RequestError, ValueError) as exc:
            logger.warning("Loki request failed: %s — empty log context", exc)
            return []


def _parse_streams(streams: list[dict]) -> list[LogLine]:
    lines: list[LogLine] = []
    for stream in streams:
        for ts_str, raw_line in stream.get("values", []):
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            lines.append(
                LogLine(
                    timestamp_ns=int(ts_str),
                    message=parsed.get("message", ""),
                    level=parsed.get("level", "UNKNOWN"),
                    exception_class=parsed.get("exception_class"),
                    request_id=parsed.get("request_id"),
                    raw=parsed,
                )
            )
    lines.sort(key=lambda x: x.timestamp_ns, reverse=True)
    return lines
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_log_fetcher.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/services/log_fetcher.py ai-bot/tests/unit/test_log_fetcher.py
git commit -m "feat(services): LogFetcher with Loki HTTP query + graceful fallback"
```

---

## Task 10: RepoManager (GitPython bare clone + worktree)

**Files:**
- Create: `ai-bot/src/ai_bot/services/repo_manager.py`
- Create: `ai-bot/tests/unit/test_repo_manager.py`

- [ ] **Step 1: 통합 테스트 작성 (실제 임시 git 레포 사용)**

Create `ai-bot/tests/unit/test_repo_manager.py`:

```python
import subprocess
from pathlib import Path

import pytest

from ai_bot.services.repo_manager import RepoManager


@pytest.fixture
def upstream_repo(tmp_path: Path) -> Path:
    """테스트용 upstream git 레포 — bare 아니라 일반"""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=upstream, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=upstream, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=upstream, check=True)
    (upstream / "README.md").write_text("v1\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=upstream, check=True)
    subprocess.run(["git", "tag", "v1"], cwd=upstream, check=True)

    (upstream / "README.md").write_text("v2\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=upstream, check=True)
    subprocess.run(["git", "tag", "v2"], cwd=upstream, check=True)

    return upstream


@pytest.mark.asyncio
async def test_first_clone_creates_bare(upstream_repo: Path, tmp_path: Path) -> None:
    mgr = RepoManager(
        clone_url=str(upstream_repo),
        cache_dir=str(tmp_path / "cache"),
        worktree_dir=str(tmp_path / "wt"),
    )
    await mgr.ensure_bare_clone()
    bare = tmp_path / "cache" / "demo.git"
    assert bare.exists()
    assert (bare / "HEAD").exists()


@pytest.mark.asyncio
async def test_checkout_at_sha_creates_worktree(upstream_repo: Path, tmp_path: Path) -> None:
    mgr = RepoManager(
        clone_url=str(upstream_repo),
        cache_dir=str(tmp_path / "cache"),
        worktree_dir=str(tmp_path / "wt"),
    )
    # v1 시점 SHA 가져오기
    v1_sha = subprocess.check_output(["git", "rev-parse", "v1"], cwd=upstream_repo, text=True).strip()
    worktree = await mgr.checkout_at_sha(v1_sha)
    try:
        assert (worktree / "README.md").read_text() == "v1\n"
    finally:
        await mgr.cleanup_worktree(worktree)


@pytest.mark.asyncio
async def test_cleanup_worktree_removes_it(upstream_repo: Path, tmp_path: Path) -> None:
    mgr = RepoManager(
        clone_url=str(upstream_repo),
        cache_dir=str(tmp_path / "cache"),
        worktree_dir=str(tmp_path / "wt"),
    )
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream_repo, text=True).strip()
    worktree = await mgr.checkout_at_sha(sha)
    await mgr.cleanup_worktree(worktree)
    assert not worktree.exists()
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_repo_manager.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: RepoManager 구현**

Create `ai-bot/src/ai_bot/services/repo_manager.py`:

```python
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class RepoManagerError(Exception):
    pass


class RepoManager:
    def __init__(self, *, clone_url: str, cache_dir: str, worktree_dir: str) -> None:
        self._clone_url = clone_url
        self._cache_dir = Path(cache_dir)
        self._worktree_dir = Path(worktree_dir)
        self._bare_path = self._cache_dir / "demo.git"
        self._lock = asyncio.Lock()

    async def ensure_bare_clone(self) -> Path:
        async with self._lock:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._worktree_dir.mkdir(parents=True, exist_ok=True)
            if self._bare_path.exists():
                await self._run(["git", "-C", str(self._bare_path), "fetch", "--all", "--tags", "--prune"])
            else:
                await self._run(["git", "clone", "--bare", self._clone_url, str(self._bare_path)])
            return self._bare_path

    async def checkout_at_sha(self, sha: str) -> Path:
        await self.ensure_bare_clone()
        worktree_path = self._worktree_dir / f"wt-{sha[:8]}-{uuid.uuid4().hex[:6]}"
        try:
            await self._run([
                "git", "-C", str(self._bare_path),
                "worktree", "add", "--detach", str(worktree_path), sha,
            ])
        except RepoManagerError as exc:
            raise RepoManagerError(f"failed to checkout {sha}: {exc}") from exc
        return worktree_path

    async def cleanup_worktree(self, worktree_path: Path) -> None:
        if not worktree_path.exists():
            return
        try:
            await self._run([
                "git", "-C", str(self._bare_path),
                "worktree", "remove", "--force", str(worktree_path),
            ])
        except RepoManagerError:
            # git worktree remove 실패 시 디렉토리 직접 삭제
            shutil.rmtree(worktree_path, ignore_errors=True)

    async def _run(self, cmd: list[str]) -> str:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RepoManagerError(f"{' '.join(cmd)} failed: {stderr.decode(errors='replace')}")
        return stdout.decode(errors="replace")
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_repo_manager.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/services/repo_manager.py ai-bot/tests/unit/test_repo_manager.py
git commit -m "feat(services): RepoManager with bare clone caching + worktree per SHA"
```

---

## Task 11: SlackNotifier

**Files:**
- Create: `ai-bot/src/ai_bot/services/slack_notifier.py`
- Create: `ai-bot/tests/unit/test_slack_notifier.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_slack_notifier.py`:

```python
import pytest
import respx
from httpx import Response

from ai_bot.services.slack_notifier import SlackNotifier


@pytest.mark.asyncio
@respx.mock
async def test_post_message_sends_correct_payload() -> None:
    route = respx.post("https://hooks.slack.com/services/X").mock(return_value=Response(200, text="ok"))
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/X")
    await notifier.post("Hello :wave:")
    assert route.called
    call = route.calls[-1]
    body = call.request.content.decode()
    assert "Hello :wave:" in body


@pytest.mark.asyncio
@respx.mock
async def test_dry_run_does_not_send() -> None:
    route = respx.post("https://hooks.slack.com/services/X").mock(return_value=Response(200, text="ok"))
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/X", dry_run=True)
    await notifier.post("Should not send")
    assert not route.called


@pytest.mark.asyncio
@respx.mock
async def test_failure_does_not_raise() -> None:
    respx.post("https://hooks.slack.com/services/X").mock(return_value=Response(500))
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/X")
    # best-effort: 실패해도 호출자에게 예외 전파 X
    await notifier.post("test")
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_slack_notifier.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: SlackNotifier 구현**

Create `ai-bot/src/ai_bot/services/slack_notifier.py`:

```python
import logging

import httpx

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self, *, webhook_url: str, dry_run: bool = False, timeout_seconds: float = 5.0) -> None:
        self._url = webhook_url
        self._dry_run = dry_run
        self._timeout = timeout_seconds

    async def post(self, text: str) -> None:
        if self._dry_run:
            logger.info("[DRY_RUN] slack post: %s", text)
            return
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._url, json={"text": text})
            if resp.status_code >= 400:
                logger.warning("slack post failed: status=%s body=%s", resp.status_code, resp.text)
        except httpx.RequestError as exc:
            logger.warning("slack post request error: %s", exc)
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_slack_notifier.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/services/slack_notifier.py ai-bot/tests/unit/test_slack_notifier.py
git commit -m "feat(services): SlackNotifier with dry-run + best-effort failure handling"
```

---

## Task 12: AnalysisResult 스키마 + FakeAnalyzer + Orchestrator

**Files:**
- Create: `ai-bot/src/ai_bot/analyzer/result.py`
- Create: `ai-bot/src/ai_bot/analyzer/fake.py`
- Create: `ai-bot/src/ai_bot/orchestrator.py`
- Create: `ai-bot/tests/integration/test_orchestrator.py`

Plan 2의 핵심 — 모든 컴포넌트를 엮는 Orchestrator. Analyzer는 Plan 3에서 real로 교체될 예정이므로 Plan 2에서는 `FakeAnalyzer`만.

- [ ] **Step 1: AnalysisResult 스키마**

Create `ai-bot/src/ai_bot/analyzer/result.py`:

```python
from typing import Literal

from pydantic import BaseModel, Field


class Patch(BaseModel):
    file_path: str
    old_content: str
    new_content: str


class AnalysisResult(BaseModel):
    category: Literal["CODE_BUG", "DATA_ANOMALY", "INFRA_ISSUE", "INSUFFICIENT_CONTEXT", "BENIGN_ERROR"]
    confidence: float = Field(ge=0.0, le=1.0)
    root_cause: str

    # CODE_BUG / BENIGN_ERROR
    patch: Patch | None = None

    # DATA_ANOMALY
    data_hypothesis: str | None = None
    verification_sql: list[str] = Field(default_factory=list)
    verification_logql: list[str] = Field(default_factory=list)

    # INFRA_ISSUE
    infra_checklist: list[str] = Field(default_factory=list)
    related_metrics: list[str] = Field(default_factory=list)

    # BENIGN_ERROR
    alert_rule_proposal: str | None = None

    # 메타데이터 (LLM 사용량 추적)
    tool_calls_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    model: str = "fake"
```

- [ ] **Step 2: FakeAnalyzer**

Create `ai-bot/src/ai_bot/analyzer/fake.py`:

```python
from pathlib import Path

from ai_bot.analyzer.result import AnalysisResult


class FakeAnalyzer:
    """Plan 2 단계의 stub. Plan 3에서 real Claude Agent SDK 기반으로 교체된다."""

    async def analyze(
        self,
        *,
        worktree_path: Path,
        error_class: str,
        commit_sha: str,
        log_lines: list,
    ) -> AnalysisResult:
        return AnalysisResult(
            category="CODE_BUG",
            confidence=0.85,
            root_cause=f"[FAKE] {error_class} in {worktree_path.name} (commit {commit_sha[:8]})",
            patch=None,  # Plan 2에서는 PR 생성 안 함
            model="fake",
            tool_calls_count=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=100,
        )
```

- [ ] **Step 3: Orchestrator 작성 — Plan 2 범위**

Create `ai-bot/src/ai_bot/orchestrator.py`:

```python
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from ai_bot.analyzer.result import AnalysisResult
from ai_bot.config import Settings
from ai_bot.db.models import AnalysisRun, Incident
from ai_bot.safety import cost_guard, dedup
from ai_bot.services.log_fetcher import LogFetcher, LogLine
from ai_bot.services.repo_manager import RepoManager, RepoManagerError
from ai_bot.services.slack_notifier import SlackNotifier
from ai_bot.webhook.schemas import IncidentEvent

logger = logging.getLogger(__name__)


class Analyzer(Protocol):
    async def analyze(
        self, *, worktree_path, error_class: str, commit_sha: str, log_lines: list[LogLine],
    ) -> AnalysisResult: ...


class Orchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        session_maker: async_sessionmaker[AsyncSession],
        log_fetcher: LogFetcher,
        repo_manager: RepoManager,
        slack: SlackNotifier,
        analyzer: Analyzer,
    ) -> None:
        self._settings = settings
        self._session_maker = session_maker
        self._log_fetcher = log_fetcher
        self._repo_manager = repo_manager
        self._slack = slack
        self._analyzer = analyzer

    async def handle(self, event: IncidentEvent) -> None:
        now = datetime.now(UTC)

        async with self._session_maker() as session:
            # 1. dedup
            dedup_result = await dedup.dedup_or_register(
                session, event, window_minutes=self._settings.dedup_window_minutes, now=now,
            )
            if dedup_result.kind == "DUPLICATE":
                await self._slack.post(
                    f"🔁 기존 인시던트 재발 (총 {dedup_result.occurrence_count}회) — "
                    f"{event.service} @ {event.commit_sha[:8]} {event.error_class}"
                )
                return

            # 2. cost cap
            allowed = await cost_guard.check_daily_cap(
                session, cap_usd=self._settings.daily_cost_cap_usd, now=now,
            )
            if not allowed:
                await self._slack.post(
                    f"💸 일일 LLM 비용 cap (${self._settings.daily_cost_cap_usd}) 초과 — 분석 거절"
                )
                return

            # 3. run 시작
            run = AnalysisRun(incident_id=dedup_result.incident_id, status="ANALYZING", started_at=now)
            session.add(run)
            await session.commit()
            await session.refresh(run)

            await self._slack.post(
                f"🚨 에러 감지 — {event.service} @ {event.commit_sha[:8]} "
                f"({event.error_class})"
            )

            # 4. 로그 + worktree 준비 + 분석
            worktree = None
            try:
                logs = await self._log_fetcher.fetch_recent_errors(
                    service=event.service,
                    commit_sha=event.commit_sha,
                    window_minutes=self._settings.log_query_window_minutes,
                )
                worktree = await self._repo_manager.checkout_at_sha(event.commit_sha)
                await self._slack.post(
                    f"🔍 분석 시작 — Claude Agent가 코드를 탐색 (로그 {len(logs)}건, "
                    f"worktree: {worktree.name})"
                )

                start = time.monotonic()
                result = await self._analyzer.analyze(
                    worktree_path=worktree,
                    error_class=event.error_class,
                    commit_sha=event.commit_sha,
                    log_lines=logs,
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                await cost_guard.record_usage(
                    session,
                    run_id=run.id,
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=result.cost_usd,
                    tool_calls_count=result.tool_calls_count,
                    latency_ms=latency_ms,
                )

                # 5. 결과 기록 (Plan 2: PR/Issue 생성은 아직 안 함)
                run.status = "COMPLETED"
                run.category = result.category
                run.confidence = result.confidence
                run.root_cause = result.root_cause
                run.completed_at = datetime.now(UTC)
                await session.commit()

                await self._slack.post(
                    f"✅ [FAKE] 분석 완료 — category={result.category}, "
                    f"confidence={result.confidence:.2f}, cost=${result.cost_usd:.3f}\n"
                    f"> {result.root_cause}"
                )
            except RepoManagerError as exc:
                run.status = "FAILED"
                run.error_message = str(exc)
                run.completed_at = datetime.now(UTC)
                await session.commit()
                await self._slack.post(f"❌ 코드 체크아웃 실패: {event.commit_sha[:8]} ({exc})")
            except Exception as exc:  # noqa: BLE001 — orchestrator-level safety
                logger.exception("orchestrator error")
                run.status = "FAILED"
                run.error_message = repr(exc)
                run.completed_at = datetime.now(UTC)
                await session.commit()
                await self._slack.post(f"⚠️ 분석 실패: {exc}")
            finally:
                if worktree is not None:
                    await self._repo_manager.cleanup_worktree(worktree)
```

- [ ] **Step 4: Orchestrator 통합 테스트 작성**

Create `ai-bot/tests/integration/test_orchestrator.py`:

```python
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_bot.analyzer.fake import FakeAnalyzer
from ai_bot.analyzer.result import AnalysisResult
from ai_bot.config import Settings
from ai_bot.db.models import Base, Incident
from ai_bot.orchestrator import Orchestrator
from ai_bot.services.log_fetcher import LogFetcher
from ai_bot.services.repo_manager import RepoManager
from ai_bot.services.slack_notifier import SlackNotifier
from ai_bot.webhook.schemas import IncidentEvent


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/owner/repo.git")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DRY_RUN", "true")
    return Settings()  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def session_maker(tmp_path: Path) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_handle_first_incident_completes(settings, session_maker, tmp_path: Path) -> None:
    fake_logs: list = []
    log_fetcher = AsyncMock(spec=LogFetcher)
    log_fetcher.fetch_recent_errors.return_value = fake_logs

    repo_manager = AsyncMock(spec=RepoManager)
    repo_manager.checkout_at_sha.return_value = tmp_path / "wt"
    repo_manager.cleanup_worktree.return_value = None

    slack = SlackNotifier(webhook_url="x", dry_run=True)
    analyzer = FakeAnalyzer()

    orch = Orchestrator(
        settings=settings,
        session_maker=session_maker,
        log_fetcher=log_fetcher,
        repo_manager=repo_manager,
        slack=slack,
        analyzer=analyzer,
    )
    event = IncidentEvent(service="demo-buggy-service", commit_sha="abc123", error_class="NPE")
    await orch.handle(event)

    repo_manager.checkout_at_sha.assert_awaited_once()
    repo_manager.cleanup_worktree.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_event_skips_analysis(settings, session_maker, tmp_path: Path) -> None:
    log_fetcher = AsyncMock(spec=LogFetcher)
    log_fetcher.fetch_recent_errors.return_value = []
    repo_manager = AsyncMock(spec=RepoManager)
    repo_manager.checkout_at_sha.return_value = tmp_path / "wt"

    slack = SlackNotifier(webhook_url="x", dry_run=True)
    orch = Orchestrator(
        settings=settings, session_maker=session_maker,
        log_fetcher=log_fetcher, repo_manager=repo_manager,
        slack=slack, analyzer=FakeAnalyzer(),
    )
    event = IncidentEvent(service="demo-buggy-service", commit_sha="abc", error_class="NPE")

    await orch.handle(event)
    await orch.handle(event)  # 즉시 두 번째 호출 → DUPLICATE

    assert repo_manager.checkout_at_sha.await_count == 1  # 두 번째는 dedup으로 분석 안 함


@pytest.mark.asyncio
async def test_repo_failure_marks_run_failed(settings, session_maker, tmp_path: Path) -> None:
    from ai_bot.services.repo_manager import RepoManagerError

    log_fetcher = AsyncMock(spec=LogFetcher)
    log_fetcher.fetch_recent_errors.return_value = []
    repo_manager = AsyncMock(spec=RepoManager)
    repo_manager.checkout_at_sha.side_effect = RepoManagerError("clone failed")

    slack = SlackNotifier(webhook_url="x", dry_run=True)
    orch = Orchestrator(
        settings=settings, session_maker=session_maker,
        log_fetcher=log_fetcher, repo_manager=repo_manager,
        slack=slack, analyzer=FakeAnalyzer(),
    )
    event = IncidentEvent(service="demo-buggy-service", commit_sha="abc", error_class="NPE")
    await orch.handle(event)
    repo_manager.cleanup_worktree.assert_not_awaited()
```

- [ ] **Step 5: 테스트 실행**

Run:
```bash
cd ai-bot
uv run pytest tests/integration/test_orchestrator.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/analyzer/ ai-bot/src/ai_bot/orchestrator.py \
        ai-bot/tests/integration/test_orchestrator.py
git commit -m "feat(orchestrator): assemble pipeline with FakeAnalyzer (Plan 3에서 교체)"
```

---

## Task 13: FastAPI main.py + lifespan + DI

**Files:**
- Create: `ai-bot/src/ai_bot/main.py`

- [ ] **Step 1: main.py 작성**

Create `ai-bot/src/ai_bot/main.py`:

```python
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_bot.analyzer.fake import FakeAnalyzer
from ai_bot.config import Settings
from ai_bot.db.session import create_engine, create_session_maker
from ai_bot.orchestrator import Orchestrator
from ai_bot.services.log_fetcher import LogFetcher
from ai_bot.services.repo_manager import RepoManager
from ai_bot.services.slack_notifier import SlackNotifier
from ai_bot.webhook.receiver import build_router
from ai_bot.webhook.schemas import IncidentEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings()  # type: ignore[call-arg]

    engine = create_engine(s.db_path)
    session_maker = create_session_maker(engine)

    log_fetcher = LogFetcher(loki_url=s.loki_url)
    repo_manager = RepoManager(
        clone_url=s.github_repo_url,
        cache_dir=s.repo_cache_dir,
        worktree_dir=s.worktree_dir,
    )
    slack = SlackNotifier(webhook_url=s.slack_webhook_url, dry_run=s.dry_run)
    analyzer = FakeAnalyzer()

    orchestrator = Orchestrator(
        settings=s,
        session_maker=session_maker,
        log_fetcher=log_fetcher,
        repo_manager=repo_manager,
        slack=slack,
        analyzer=analyzer,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # bare clone 준비 (실패해도 봇은 기동)
        try:
            await repo_manager.ensure_bare_clone()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure_bare_clone failed at startup: %s — will retry per request", exc)
        logger.info("ai-bot ready (dry_run=%s)", s.dry_run)
        yield
        await engine.dispose()

    app = FastAPI(title="ai-bot", lifespan=lifespan)

    async def on_incident(event: IncidentEvent) -> None:
        await orchestrator.handle(event)

    app.include_router(build_router(settings=s, on_incident=on_incident))

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "dry_run": s.dry_run}

    return app


app = create_app()
```

- [ ] **Step 2: 로컬 기동 검증**

Run:
```bash
cd ai-bot
WEBHOOK_TOKEN=dev-token LOKI_URL=http://localhost:3100 \
GITHUB_REPO=kiekk/demo-buggy-service \
GITHUB_REPO_URL=https://github.com/kiekk/demo-buggy-service.git \
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/dummy \
DB_PATH=/tmp/ai-bot-dev.db DRY_RUN=true \
REPO_CACHE_DIR=/tmp/ai-bot-repos WORKTREE_DIR=/tmp/ai-bot-wt \
uv run uvicorn ai_bot.main:app --host 0.0.0.0 --port 8090 &
SERVER_PID=$!
sleep 5
curl -s http://localhost:8090/health
echo
# 모의 webhook
curl -s -X POST http://localhost:8090/webhooks/grafana \
    -H "Authorization: Bearer dev-token" \
    -H "Content-Type: application/json" \
    -d '{
      "status":"firing",
      "alerts":[{"status":"firing","labels":{"service":"demo-buggy-service","commit_sha":"abc123"},"annotations":{},"startsAt":"2026-06-17T12:00:00Z"}],
      "commonLabels":{"service":"demo-buggy-service","commit_sha":"abc123"},
      "groupLabels":{}
    }'
echo
sleep 3
kill $SERVER_PID 2>/dev/null
```

Expected:
- `/health` 응답: `{"status":"ok","dry_run":true}`
- `/webhooks/grafana` 응답: 202 또는 `{"service":"demo-buggy-service","commit_sha":"abc123"}`
- 콘솔에 `[DRY_RUN] slack post:` 메시지 여러 줄 (감지/분석시작/분석완료)

> 만약 webhook 응답 후 콘솔에 RepoManagerError가 보이면 정상 — Plan 2 테스트 환경에선 demo-buggy-service에 `abc123` 커밋이 없기 때문. dry_run이라 외부 영향은 0.

- [ ] **Step 3: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/main.py
git commit -m "feat(main): FastAPI app with lifespan, DI, /health endpoint"
```

---

## Task 14: Dockerfile + docker-compose에 ai-bot 추가 (webhook-echo 제거)

**Files:**
- Create: `ai-bot/Dockerfile`
- Create: `ai-bot/README.md`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Dockerfile 작성**

Create `ai-bot/Dockerfile`:

```dockerfile
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
```

- [ ] **Step 2: README.md (봇 단독 가이드)**

Create `ai-bot/README.md`:

```markdown
# ai-bot

AI Incident Bot — Grafana Webhook을 수신해 코드 분석 + PR 생성 자동화.

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

## docker로 풀세트 기동

```bash
cd ..
docker compose --profile demo up -d --build
```
```

- [ ] **Step 3: docker-compose.yml 수정 — webhook-echo 제거 + ai-bot 추가**

기존 `webhook-echo` 서비스를 제거하고 `ai-bot` 서비스를 추가한다. 전체 `docker-compose.yml`을 다음으로 교체 (기존 services 유지 + 변경):

```yaml
services:
  loki:
    image: grafana/loki:2.9.3
    container_name: loki
    ports:
      - "3100:3100"
    volumes:
      - ./infra/loki/loki-config.yaml:/etc/loki/loki-config.yaml
      - loki_data:/loki
    command: -config.file=/etc/loki/loki-config.yaml
    networks:
      - observability-net
    restart: unless-stopped

  grafana:
    image: grafana/grafana:10.2.3
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_LOG_LEVEL=info
      - GF_UNIFIED_ALERTING_ENABLED=true
      - GF_ALERTING_ENABLED=false
      - AI_BOT_WEBHOOK_URL=${AI_BOT_WEBHOOK_URL:-http://ai-bot:8090/webhooks/grafana}
      - WEBHOOK_TOKEN=${WEBHOOK_TOKEN:-dev-token}
    volumes:
      - ./infra/grafana/provisioning:/etc/grafana/provisioning
      - ./infra/grafana/dashboards:/etc/grafana/dashboards
      - grafana_data:/var/lib/grafana
    networks:
      - observability-net
    depends_on:
      - loki
    restart: unless-stopped

  alloy:
    image: grafana/alloy:v1.0.0
    container_name: alloy
    volumes:
      - ./infra/alloy/alloy.hcl:/etc/alloy/config.alloy
      - /var/run/docker.sock:/var/run/docker.sock
    command: run --server.http.listen-addr=0.0.0.0:12345 --storage.path=/var/lib/alloy/data /etc/alloy/config.alloy
    ports:
      - "12345:12345"
    networks:
      - observability-net
    depends_on:
      - loki
    restart: unless-stopped

  loadgen:
    image: grafana/k6:0.48.0
    container_name: loadgen
    volumes:
      - ./infra/loadgen/k6:/scripts
    networks:
      - observability-net
    command: ["run", "/scripts/smoke.js"]
    profiles:
      - loadtest

  postgres:
    image: postgres:16-alpine
    container_name: postgres
    environment:
      - POSTGRES_DB=buggy
      - POSTGRES_USER=buggy
      - POSTGRES_PASSWORD=buggy
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    networks:
      - observability-net
    profiles:
      - demo
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U buggy"]
      interval: 5s
      timeout: 5s
      retries: 5

  buggy-service:
    build:
      context: ./demo-buggy-service
    container_name: buggy-service
    ports:
      - "8081:8080"
    environment:
      - SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/buggy
      - SPRING_DATASOURCE_USERNAME=buggy
      - SPRING_DATASOURCE_PASSWORD=buggy
      - SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=${HIKARI_MAX_POOL:-10}
    networks:
      - observability-net
    profiles:
      - demo
    depends_on:
      postgres:
        condition: service_healthy

  ai-bot:
    build: ./ai-bot
    container_name: ai-bot
    ports:
      - "8090:8090"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-not-used-in-plan-2}
      - GITHUB_TOKEN=${GITHUB_TOKEN:-not-used-in-plan-2}
      - GITHUB_REPO=${GITHUB_REPO}
      - GITHUB_REPO_URL=${GITHUB_REPO_URL}
      - LOKI_URL=http://loki:3100
      - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
      - WEBHOOK_TOKEN=${WEBHOOK_TOKEN:-dev-token}
      - DRY_RUN=${DRY_RUN:-false}
      - DAILY_COST_CAP_USD=${DAILY_COST_CAP_USD:-5}
    volumes:
      - ai_bot_data:/data
    networks:
      - observability-net
    profiles:
      - demo
    depends_on:
      - loki
    restart: unless-stopped

networks:
  observability-net:
    driver: bridge

volumes:
  grafana_data:
  loki_data:
  postgres_data:
  ai_bot_data:
```

- [ ] **Step 4: 기존 webhook-echo 디렉토리 삭제**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
rm -rf tools/webhook-echo
```

- [ ] **Step 5: Commit**

```bash
git add ai-bot/Dockerfile ai-bot/README.md docker-compose.yml
git rm -r tools/webhook-echo
git commit -m "feat(compose): replace webhook-echo with ai-bot service in demo profile"
```

---

## Task 15: End-to-end Plan 2 검증

**Files:** (변경 없음, 검증만)

- [ ] **Step 1: 풀세트 기동 (build 포함)**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose --profile demo down -v
docker compose --profile demo up -d --build
sleep 60
docker compose ps
```

Expected: `ai-bot`, `buggy-service`, `postgres`, `loki`, `grafana`, `alloy` 모두 `Up`. (ai-bot은 health endpoint 200 OK)

- [ ] **Step 2: ai-bot health 확인**

Run:
```bash
curl -s http://localhost:8090/health
```

Expected: `{"status":"ok","dry_run":false}` (또는 dry_run=true)

- [ ] **Step 3: ai-bot 초기화 로그 확인**

Run:
```bash
docker compose logs ai-bot | tail -30
```

Expected: 다음 메시지 포함:
- `alembic upgrade head` 성공
- `ensure_bare_clone` 성공 (demo-buggy-service clone 완료) 또는 실패 메시지 (private repo이고 token 미설정일 경우)

> private repo인데 clone이 실패하면, `GITHUB_REPO_URL`을 token 포함 URL로 변경:
> `https://x-access-token:${GITHUB_TOKEN}@github.com/kiekk/demo-buggy-service.git`

- [ ] **Step 4: 시나리오 1 트리거 후 봇 동작 확인**

Run:
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js
sleep 90  # alert 평가 + webhook 전달 + 분석
docker compose logs ai-bot | tail -50
```

Expected (ai-bot 로그):
- `received_at` 비슷한 webhook 수신 로그
- `[FAKE]` 메시지가 포함된 분석 완료 로그
- 또는 Slack 메시지 발송 로그 (DRY_RUN=false 시)

- [ ] **Step 5: SQLite DB에 incident/run 기록 확인**

Run:
```bash
docker compose exec ai-bot sqlite3 /data/ai-bot.db ".tables"
docker compose exec ai-bot sqlite3 /data/ai-bot.db "SELECT id, service, commit_sha, error_class, occurrence_count FROM incidents;"
docker compose exec ai-bot sqlite3 /data/ai-bot.db "SELECT id, incident_id, status, category, confidence FROM analysis_runs;"
```

Expected:
- 테이블: `alembic_version analysis_runs incidents llm_usage`
- incidents row 1개 이상 (시나리오 1 fingerprint)
- analysis_runs row 1개 이상 (status `COMPLETED`, category `CODE_BUG`)

- [ ] **Step 6: Slack 알림 수신 확인 (실제 webhook 사용 시)**

DRY_RUN=false + 실제 SLACK_WEBHOOK_URL 설정 상태에서, Slack 채널에 다음 메시지들이 와야 함:
- 🚨 에러 감지
- 🔍 분석 시작
- ✅ [FAKE] 분석 완료

- [ ] **Step 7: 정리**

Run:
```bash
docker compose --profile demo down
```

- [ ] **Step 8: README 갱신**

`README.md`의 "AI Incident Bot 데모 (Plan 1)" 섹션을 "Plan 2"로 갱신:

```markdown
## AI Incident Bot 데모 (Plan 2)

### 실행

```bash
cp .env.example .env
# .env 편집: WEBHOOK_TOKEN, SLACK_WEBHOOK_URL 등 채우기
git submodule update --init --recursive
docker compose --profile demo up -d --build
```

### 시나리오 트리거

(Plan 1 동일)

### 검증

- Grafana: http://localhost:3000 (admin/admin)
- ai-bot health: http://localhost:8090/health
- ai-bot 로그: `docker compose logs -f ai-bot`
- DB: `docker compose exec ai-bot sqlite3 /data/ai-bot.db "SELECT * FROM analysis_runs;"`
- Slack: 채널에서 단계별 메시지 확인

> Plan 2 단계에서는 Analyzer가 FakeAnalyzer로 stub되어 실제 LLM 호출/PR 생성은 하지 않음. Plan 3에서 Claude Agent SDK + GitHubClient로 교체.
```

- [ ] **Step 9: Final commit**

```bash
git add README.md
git commit -m "docs: update README for Plan 2 (ai-bot replaces webhook-echo)"
```

---

## Plan 2 Out of Scope

- Claude Agent SDK 실제 호출 — Plan 3
- 도구 7종 (read_file, grep, git_log, git_diff, read_db_schema, propose_patch, report_finding) — Plan 3
- GitHubClient (Issue/PR 자동 생성) — Plan 3
- 시나리오 4 (DATA_ANOMALY), 5 (INFRA_ISSUE), 6 (BENIGN_ERROR) — Plan 4
- ai-bot 자체 Grafana 대시보드 — Plan 4
- DEMO_GUIDE.md — Plan 4

---

## Plan 2 완료 시 산출물

- `docker compose --profile demo up -d --build` 한 줄로 ai-bot 포함 모든 서비스 기동
- Grafana Alert 발화 시 ai-bot이 webhook 수신 → dedup → log fetch → worktree 생성 → Slack 알림
- SQLite에 incident/run 기록 + dedup 윈도우 동작
- DRY_RUN 모드 전환 가능
- 모든 컴포넌트 단위 테스트 + Orchestrator 통합 테스트 (FakeAnalyzer 사용) 통과
