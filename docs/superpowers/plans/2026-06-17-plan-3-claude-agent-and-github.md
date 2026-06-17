# Plan 3: Claude Agent SDK + GitHub 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plan 2의 `FakeAnalyzer`를 진짜 Claude Agent SDK 기반 `ClaudeAnalyzer`로 교체하고, GitHubClient로 Issue/Draft PR을 자동 생성한다. 시나리오 1~3 (CODE_BUG) end-to-end로 PR이 GitHub에 생성되는 것까지 검증.

**Architecture:** Claude Agent SDK Python이 Claude Code CLI를 subprocess로 spawn해서 도구 호출을 처리한다. 7개 in-process Python 도구(`read_file`, `grep`, `git_log`, `git_diff`, `read_db_schema`, `propose_patch`, `report_finding`)를 등록. `report_finding`이 호출되면 `AnalysisResult`를 종결값으로 받아 Orchestrator로 반환. PR 생성은 PyGithub으로 처리, 항상 Draft 상태 + `human-review-required` 라벨.

**Tech Stack:**
- `claude-agent-sdk` (Python) — Claude Agent SDK 최신
- `PyGithub` 2.x — GitHub Issue/PR API
- Plan 2 스택 유지 (FastAPI/SQLAlchemy/GitPython/slack-sdk)

**관련 문서:**
- spec: `docs/superpowers/specs/2026-06-16-ai-incident-bot-demo-design.md` (Phase 6~7, 카테고리 분류, 도구 7종)
- 이전 plan: `docs/superpowers/plans/2026-06-17-plan-2-ai-bot-core.md` 완료 가정

---

## 사전 작업

- [ ] **A. Plan 2 완료 확인**
  - `docker compose --profile demo up -d --build`로 ai-bot 포함 풀세트 기동
  - 시나리오 1 트리거 시 ai-bot 로그에 `[FAKE]` 분석 완료 메시지가 보이고 SQLite에 row 생성

- [ ] **B. Anthropic API key 확인**
  - `.env`에 `ANTHROPIC_API_KEY=sk-ant-...` 있는지 확인 (Plan 2에서 셋업 완료)
  - 또는 Claude Code CLI 활용: `claude` 명령으로 Max 구독 로그인 (개발 모드에서만)

- [ ] **C. GITHUB_TOKEN 확인 + repo 권한 검증**

`.env`에 `GITHUB_TOKEN=ghp_...` 있는지 확인 후:

```bash
source ~/Documents/study/demo-log-observability/demo-log-observability/.env
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
    https://api.github.com/repos/$GITHUB_REPO | python3 -c "import sys,json;d=json.load(sys.stdin);print('repo:',d.get('full_name'),'permissions:',d.get('permissions'))"
```

Expected: `repo: kiekk/demo-buggy-service permissions: {'admin': True, 'push': True, ...}`

- [ ] **D. demo-buggy-service main 브랜치 protection 켜기 (권장)**

GitHub → `kiekk/demo-buggy-service` → Settings → Branches → Add rule:
- Branch name pattern: `main`
- ✅ Require a pull request before merging
- ✅ Require approvals: 1
- Save

> 이유: AI가 만든 Draft PR을 실수로 머지하면 의도적 버그가 사라져 시나리오 재현 불가.

---

## File Structure

```
$REPO/ai-bot/
├── pyproject.toml                              (Task 1 수정 — claude-agent-sdk + PyGithub)
├── src/ai_bot/
│   ├── analyzer/
│   │   ├── claude.py                           (Task 9 — ClaudeAnalyzer)
│   │   ├── prompts.py                          (Task 8 — system prompt)
│   │   ├── tools/                              ★ 신규 디렉토리
│   │   │   ├── __init__.py                     (Task 2)
│   │   │   ├── filesystem.py                   (Task 2 — read_file, grep)
│   │   │   ├── git_history.py                  (Task 4 — git_log, git_diff)
│   │   │   ├── db_schema.py                    (Task 5 — read_db_schema)
│   │   │   ├── patch.py                        (Task 6 — propose_patch)
│   │   │   └── finding.py                      (Task 7 — report_finding)
│   │   ├── result.py                           (Plan 2에서 이미 존재, 변경 없음)
│   │   └── fake.py                             (보존 — 테스트에서 사용)
│   ├── services/
│   │   ├── github_client.py                    (Task 10/11 — Issue/PR 생성)
│   │   ├── pr_templates.py                     (Task 12 — PR/Issue 본문 템플릿)
│   │   └── (기존: log_fetcher, repo_manager, slack_notifier)
│   ├── safety/
│   │   ├── benign_cooldown.py                  (Task 13 — BENIGN 24h 차단)
│   │   └── (기존: dedup, cost_guard)
│   ├── orchestrator.py                         (Task 14 수정 — PR/Issue 분기)
│   └── main.py                                 (Task 15 수정 — ClaudeAnalyzer 주입)
└── tests/
    ├── unit/
    │   ├── test_tools_filesystem.py            (Task 2)
    │   ├── test_tools_git_history.py           (Task 4)
    │   ├── test_tools_db_schema.py             (Task 5)
    │   ├── test_tools_patch.py                 (Task 6)
    │   ├── test_tools_finding.py               (Task 7)
    │   ├── test_github_client.py               (Task 10)
    │   ├── test_pr_templates.py                (Task 12)
    │   └── test_benign_cooldown.py             (Task 13)
    └── integration/
        ├── test_claude_analyzer.py             (Task 9 — Optional, real API)
        └── test_orchestrator_with_github.py    (Task 14)
```

---

## Task 1: 의존성 추가 — claude-agent-sdk + PyGithub

**Files:**
- Modify: `ai-bot/pyproject.toml`

- [ ] **Step 1: pyproject.toml에 의존성 추가**

`ai-bot/pyproject.toml`의 `dependencies` 배열에 다음 2개 추가:

```toml
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
    "claude-agent-sdk>=0.1.0",
    "PyGithub>=2.5.0",
]
```

- [ ] **Step 2: 의존성 설치**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability/ai-bot
uv sync
uv run python -c "import claude_agent_sdk, github; print('claude-agent-sdk:', getattr(claude_agent_sdk, '__version__', 'n/a')); print('PyGithub:', github.__version__)"
```

Expected: 두 패키지 버전이 출력됨. claude-agent-sdk가 Claude Code CLI 의존성 알림 가능 — 무시.

- [ ] **Step 3: Claude Code CLI 설치 확인 (Agent SDK가 spawn함)**

Run:
```bash
which claude || npm install -g @anthropic-ai/claude-code
claude --version
```

Expected: `claude` 명령이 PATH에 있고 버전 출력.

> Docker 컨테이너에서도 Claude Code CLI가 필요. Task 16에서 ai-bot Dockerfile에 npm install 추가.

- [ ] **Step 4: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/pyproject.toml ai-bot/uv.lock
git commit -m "feat(deps): add claude-agent-sdk + PyGithub"
```

---

## Task 2: 도구 — read_file + grep (filesystem)

**Files:**
- Create: `ai-bot/src/ai_bot/analyzer/tools/__init__.py`
- Create: `ai-bot/src/ai_bot/analyzer/tools/filesystem.py`
- Create: `ai-bot/tests/unit/test_tools_filesystem.py`

Allowlist 디렉토리: `src/main/`, `src/test/`, `db/migration/` (worktree 안의 상대 경로).

- [ ] **Step 1: __init__.py + ToolContext 정의**

Create `ai-bot/src/ai_bot/analyzer/tools/__init__.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolContext:
    """모든 도구가 공유하는 컨텍스트 — worktree 경로 + 결과 누적."""
    worktree_path: Path
    findings: list = None  # report_finding에서 채움
    patches: list = None   # propose_patch에서 채움

    def __post_init__(self) -> None:
        if self.findings is None:
            self.findings = []
        if self.patches is None:
            self.patches = []


ALLOWED_PATH_PREFIXES = (
    "src/main/",
    "src/test/",
    "src/main/resources/db/migration/",
)


class ToolError(Exception):
    """도구 호출 시 발생한 사용자 가시 오류 — Claude에게 메시지로 전달됨."""
    pass


def normalize_and_validate_path(worktree: Path, relative_path: str) -> Path:
    """worktree 기준 상대 경로 → 절대 경로로 변환 + allowlist 검증.

    Args:
        worktree: worktree 루트
        relative_path: 사용자(=Claude)가 준 상대 경로

    Returns:
        검증된 절대 경로

    Raises:
        ToolError: allowlist 외 또는 worktree 밖
    """
    p = (worktree / relative_path).resolve()
    try:
        rel = p.relative_to(worktree.resolve())
    except ValueError:
        raise ToolError(f"path outside worktree: {relative_path}") from None
    rel_str = str(rel)
    if not any(rel_str.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
        raise ToolError(
            f"path not in allowlist: {rel_str}. Allowed prefixes: {ALLOWED_PATH_PREFIXES}"
        )
    return p
```

- [ ] **Step 2: 실패하는 filesystem 도구 테스트**

Create `ai-bot/tests/unit/test_tools_filesystem.py`:

```python
from pathlib import Path

import pytest

from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.filesystem import grep, read_file


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    (tmp_path / "src/main/kotlin").mkdir(parents=True)
    (tmp_path / "src/main/kotlin/Foo.kt").write_text("class Foo {\n  fun bar() {}\n}\n")
    (tmp_path / "src/main/kotlin/Bar.kt").write_text("class Bar {\n  fun baz() {}\n}\n")
    (tmp_path / "secrets.txt").write_text("super-secret\n")
    return tmp_path


def test_read_file_returns_content(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    result = read_file(ctx, relative_path="src/main/kotlin/Foo.kt")
    assert "class Foo" in result


def test_read_file_outside_allowlist_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    with pytest.raises(ToolError, match="not in allowlist"):
        read_file(ctx, relative_path="secrets.txt")


def test_read_file_escape_via_dotdot_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    with pytest.raises(ToolError):
        read_file(ctx, relative_path="src/main/../../etc/passwd")


def test_read_file_nonexistent_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    with pytest.raises(ToolError, match="not found"):
        read_file(ctx, relative_path="src/main/kotlin/Nope.kt")


def test_grep_finds_matches(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    result = grep(ctx, pattern=r"fun \w+", path_prefix="src/main")
    assert "Foo.kt" in result
    assert "Bar.kt" in result
    assert "bar()" in result or "baz()" in result


def test_grep_with_no_matches_returns_empty(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    result = grep(ctx, pattern="ZZZ_NOMATCH", path_prefix="src/main")
    assert "no matches" in result.lower()
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_filesystem.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 4: filesystem 도구 구현**

Create `ai-bot/src/ai_bot/analyzer/tools/filesystem.py`:

```python
from __future__ import annotations

import re

from ai_bot.analyzer.tools import ToolContext, ToolError, normalize_and_validate_path

MAX_FILE_BYTES = 200 * 1024  # 200KB per read
MAX_GREP_MATCHES = 50


def read_file(ctx: ToolContext, *, relative_path: str) -> str:
    """Read a file from the worktree. Returns content (truncated to 200KB)."""
    abs_path = normalize_and_validate_path(ctx.worktree_path, relative_path)
    if not abs_path.exists():
        raise ToolError(f"file not found: {relative_path}")
    if not abs_path.is_file():
        raise ToolError(f"not a file: {relative_path}")
    data = abs_path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        return data[:MAX_FILE_BYTES].decode(errors="replace") + f"\n\n[...truncated, {len(data)} bytes total]"
    return data.decode(errors="replace")


def grep(ctx: ToolContext, *, pattern: str, path_prefix: str = "src/main") -> str:
    """Search files in the worktree for a regex pattern. Returns matches with file:line context."""
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ToolError(f"invalid regex: {exc}") from exc

    # Allowlist root 확인
    root = normalize_and_validate_path(ctx.worktree_path, path_prefix)
    if not root.exists():
        raise ToolError(f"path_prefix not found: {path_prefix}")

    matches: list[str] = []
    for file in root.rglob("*"):
        if not file.is_file():
            continue
        try:
            text = file.read_text(errors="replace")
        except OSError:
            continue
        rel = file.relative_to(ctx.worktree_path)
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{rel}:{i}: {line.strip()}")
                if len(matches) >= MAX_GREP_MATCHES:
                    matches.append(f"[...stopped at {MAX_GREP_MATCHES} matches]")
                    return "\n".join(matches)
    if not matches:
        return f"no matches for {pattern!r} in {path_prefix}"
    return "\n".join(matches)
```

- [ ] **Step 5: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_filesystem.py -v
```

Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/analyzer/tools/__init__.py \
        ai-bot/src/ai_bot/analyzer/tools/filesystem.py \
        ai-bot/tests/unit/test_tools_filesystem.py
git commit -m "feat(tools): read_file + grep with allowlist enforcement"
```

---

## Task 3: 도구 — read_file + grep — (Task 2와 통합됨, 별도 task 없음. 다음은 Task 4)

> Task 3 번호는 의도적으로 skip — filesystem 도구를 Task 2에 묶었다.

---

## Task 4: 도구 — git_log + git_diff

**Files:**
- Create: `ai-bot/src/ai_bot/analyzer/tools/git_history.py`
- Create: `ai-bot/tests/unit/test_tools_git_history.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_tools_git_history.py`:

```python
import subprocess
from pathlib import Path

import pytest

from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.git_history import git_diff, git_log


@pytest.fixture
def git_worktree(tmp_path: Path) -> Path:
    """Init a git repo with two commits for testing."""
    (tmp_path / "src/main").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)

    (tmp_path / "src/main/A.kt").write_text("v1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)

    (tmp_path / "src/main/A.kt").write_text("v2\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=tmp_path, check=True)
    return tmp_path


def test_git_log_returns_commits(git_worktree: Path) -> None:
    ctx = ToolContext(worktree_path=git_worktree)
    result = git_log(ctx, relative_path="src/main/A.kt", limit=10)
    assert "first" in result
    assert "second" in result


def test_git_log_no_path_returns_all(git_worktree: Path) -> None:
    ctx = ToolContext(worktree_path=git_worktree)
    result = git_log(ctx, relative_path=None, limit=5)
    assert "first" in result
    assert "second" in result


def test_git_log_path_outside_allowlist_raises(git_worktree: Path) -> None:
    ctx = ToolContext(worktree_path=git_worktree)
    (git_worktree / "outside.txt").write_text("x")
    with pytest.raises(ToolError):
        git_log(ctx, relative_path="outside.txt", limit=5)


def test_git_diff_between_revisions(git_worktree: Path) -> None:
    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_worktree, text=True).strip()
    prev_sha = subprocess.check_output(["git", "rev-parse", "HEAD~1"], cwd=git_worktree, text=True).strip()

    ctx = ToolContext(worktree_path=git_worktree)
    result = git_diff(ctx, base=prev_sha, head=head_sha, relative_path="src/main/A.kt")
    assert "v1" in result and "v2" in result
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_git_history.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: git_history 도구 구현**

Create `ai-bot/src/ai_bot/analyzer/tools/git_history.py`:

```python
from __future__ import annotations

import subprocess

from ai_bot.analyzer.tools import ToolContext, ToolError, normalize_and_validate_path

MAX_OUTPUT_BYTES = 50 * 1024


def _run_git(cwd, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise ToolError("git command timed out") from None
    if proc.returncode != 0:
        raise ToolError(f"git failed: {proc.stderr.strip()[:500]}")
    out = proc.stdout
    if len(out.encode()) > MAX_OUTPUT_BYTES:
        return out[:MAX_OUTPUT_BYTES] + "\n[...truncated]"
    return out


def git_log(ctx: ToolContext, *, relative_path: str | None, limit: int = 10) -> str:
    """Show recent commits affecting an optional path. Date + author + subject."""
    args = ["log", f"-n{max(1, min(limit, 50))}", "--pretty=format:%h %ad %an %s", "--date=short"]
    if relative_path:
        normalize_and_validate_path(ctx.worktree_path, relative_path)  # 검증만
        args.extend(["--", relative_path])
    return _run_git(ctx.worktree_path, args) or "(no commits)"


def git_diff(
    ctx: ToolContext, *, base: str, head: str, relative_path: str | None = None,
) -> str:
    """Show diff between two revisions, optionally limited to a path."""
    args = ["diff", f"{base}..{head}"]
    if relative_path:
        normalize_and_validate_path(ctx.worktree_path, relative_path)
        args.extend(["--", relative_path])
    return _run_git(ctx.worktree_path, args) or "(no changes)"
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_git_history.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/analyzer/tools/git_history.py \
        ai-bot/tests/unit/test_tools_git_history.py
git commit -m "feat(tools): git_log + git_diff with path validation"
```

---

## Task 5: 도구 — read_db_schema

**Files:**
- Create: `ai-bot/src/ai_bot/analyzer/tools/db_schema.py`
- Create: `ai-bot/tests/unit/test_tools_db_schema.py`

스키마 정보를 운영 DB에서가 아니라 `src/main/resources/db/migration/*.sql`에서 읽는다 (회사 PoC 안전성).

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_tools_db_schema.py`:

```python
from pathlib import Path

import pytest

from ai_bot.analyzer.tools import ToolContext
from ai_bot.analyzer.tools.db_schema import read_db_schema


@pytest.fixture
def worktree_with_migrations(tmp_path: Path) -> Path:
    mig = tmp_path / "src/main/resources/db/migration"
    mig.mkdir(parents=True)
    (mig / "V1__init.sql").write_text(
        "CREATE TABLE users (id BIGSERIAL PRIMARY KEY, name VARCHAR(255));\n"
        "CREATE TABLE addresses (id BIGSERIAL PRIMARY KEY, user_id BIGINT, city VARCHAR(255));\n"
    )
    (mig / "V2__seed.sql").write_text("INSERT INTO users (name) VALUES ('Alice');\n")
    return tmp_path


def test_read_db_schema_returns_all_migrations_concatenated(worktree_with_migrations: Path) -> None:
    ctx = ToolContext(worktree_path=worktree_with_migrations)
    result = read_db_schema(ctx, table=None)
    assert "CREATE TABLE users" in result
    assert "CREATE TABLE addresses" in result
    assert "INSERT INTO users" in result
    assert "V1__init.sql" in result
    assert "V2__seed.sql" in result


def test_read_db_schema_filters_by_table(worktree_with_migrations: Path) -> None:
    ctx = ToolContext(worktree_path=worktree_with_migrations)
    result = read_db_schema(ctx, table="addresses")
    assert "addresses" in result
    # users 테이블 만든 statement는 안 들어가야 함 (CREATE) — INSERT는 'users' 키워드라 들어갈 수 있음
    # 단순 키워드 기반 필터링이므로 약간 noisy해도 OK


def test_read_db_schema_no_migrations_returns_message(tmp_path: Path) -> None:
    ctx = ToolContext(worktree_path=tmp_path)
    result = read_db_schema(ctx, table=None)
    assert "no migration files" in result.lower()
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_db_schema.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: db_schema 도구 구현**

Create `ai-bot/src/ai_bot/analyzer/tools/db_schema.py`:

```python
from __future__ import annotations

from ai_bot.analyzer.tools import ToolContext

MIGRATION_RELPATH = "src/main/resources/db/migration"
MAX_OUTPUT_BYTES = 50 * 1024


def read_db_schema(ctx: ToolContext, *, table: str | None = None) -> str:
    """Read Flyway migration files from the worktree. Optionally filter by table name (keyword)."""
    mig_dir = ctx.worktree_path / MIGRATION_RELPATH
    if not mig_dir.exists():
        return f"no migration files found at {MIGRATION_RELPATH}"

    files = sorted(mig_dir.glob("V*.sql"))
    if not files:
        return f"no migration files found at {MIGRATION_RELPATH}"

    chunks: list[str] = []
    for f in files:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        if table and table.lower() not in text.lower():
            continue
        chunks.append(f"-- {f.name} --\n{text}")

    if not chunks:
        return f"no migration files contained {table!r}"

    joined = "\n\n".join(chunks)
    if len(joined.encode()) > MAX_OUTPUT_BYTES:
        return joined[:MAX_OUTPUT_BYTES] + "\n[...truncated]"
    return joined
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_db_schema.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/analyzer/tools/db_schema.py \
        ai-bot/tests/unit/test_tools_db_schema.py
git commit -m "feat(tools): read_db_schema from Flyway migration files"
```

---

## Task 6: 도구 — propose_patch

**Files:**
- Create: `ai-bot/src/ai_bot/analyzer/tools/patch.py`
- Create: `ai-bot/tests/unit/test_tools_patch.py`

`propose_patch`는 단일 파일 + 30라인 이하만 허용. 결과는 `ToolContext.patches`에 누적.

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_tools_patch.py`:

```python
from pathlib import Path

import pytest

from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.patch import propose_patch


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    src = tmp_path / "src/main/kotlin"
    src.mkdir(parents=True)
    (src / "Foo.kt").write_text("fun bar() {}\n")
    return tmp_path


def test_propose_patch_records_in_context(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    result = propose_patch(
        ctx, file_path="src/main/kotlin/Foo.kt",
        old_content="fun bar() {}\n",
        new_content="fun bar(): Int = 0\n",
    )
    assert "registered" in result.lower()
    assert len(ctx.patches) == 1
    assert ctx.patches[0].file_path == "src/main/kotlin/Foo.kt"
    assert ctx.patches[0].new_content == "fun bar(): Int = 0\n"


def test_propose_patch_outside_allowlist_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    with pytest.raises(ToolError):
        propose_patch(
            ctx, file_path=".env",
            old_content="x", new_content="y",
        )


def test_propose_patch_over_30_lines_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    long_new = "line\n" * 31
    with pytest.raises(ToolError, match="30 line"):
        propose_patch(
            ctx, file_path="src/main/kotlin/Foo.kt",
            old_content="fun bar() {}\n",
            new_content=long_new,
        )


def test_propose_patch_replaces_previous(worktree: Path) -> None:
    """동일 파일에 두 번째 호출 시 마지막 것만 유지."""
    ctx = ToolContext(worktree_path=worktree)
    propose_patch(
        ctx, file_path="src/main/kotlin/Foo.kt",
        old_content="fun bar() {}\n", new_content="v1\n",
    )
    propose_patch(
        ctx, file_path="src/main/kotlin/Foo.kt",
        old_content="fun bar() {}\n", new_content="v2\n",
    )
    assert len(ctx.patches) == 1
    assert ctx.patches[0].new_content == "v2\n"
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_patch.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: patch 도구 구현**

Create `ai-bot/src/ai_bot/analyzer/tools/patch.py`:

```python
from __future__ import annotations

from ai_bot.analyzer.result import Patch
from ai_bot.analyzer.tools import ToolContext, ToolError, normalize_and_validate_path

MAX_PATCH_LINES = 30


def propose_patch(
    ctx: ToolContext, *, file_path: str, old_content: str, new_content: str,
) -> str:
    """Register a single-file patch (replace old_content with new_content).

    Restrictions: file must be in allowlist, new_content must be <= 30 lines.
    Calling again on the same file_path replaces the previous patch.
    """
    normalize_and_validate_path(ctx.worktree_path, file_path)  # allowlist + worktree 검증

    new_line_count = len(new_content.splitlines())
    if new_line_count > MAX_PATCH_LINES:
        raise ToolError(f"patch exceeds {MAX_PATCH_LINES} line limit (got {new_line_count})")

    # 기존 동일 파일 patch 제거
    ctx.patches = [p for p in ctx.patches if p.file_path != file_path]
    ctx.patches.append(Patch(file_path=file_path, old_content=old_content, new_content=new_content))
    return f"patch registered for {file_path} ({new_line_count} lines)"
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_patch.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/analyzer/tools/patch.py \
        ai-bot/tests/unit/test_tools_patch.py
git commit -m "feat(tools): propose_patch with single-file + 30-line limit"
```

---

## Task 7: 도구 — report_finding

**Files:**
- Create: `ai-bot/src/ai_bot/analyzer/tools/finding.py`
- Create: `ai-bot/tests/unit/test_tools_finding.py`

`report_finding`은 Claude의 최종 보고를 받아 `AnalysisResult`로 변환. ToolContext.findings에 저장.

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_tools_finding.py`:

```python
from pathlib import Path

import pytest

from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.finding import report_finding


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(worktree_path=tmp_path)


def test_code_bug_with_patch_records_finding(ctx: ToolContext) -> None:
    from ai_bot.analyzer.result import Patch
    ctx.patches.append(Patch(file_path="src/main/x.kt", old_content="a", new_content="b"))
    result = report_finding(
        ctx, category="CODE_BUG", confidence=0.85, root_cause="NPE in X",
    )
    assert "recorded" in result.lower()
    assert len(ctx.findings) == 1
    assert ctx.findings[0].category == "CODE_BUG"
    assert ctx.findings[0].patch is not None


def test_code_bug_without_patch_raises(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="patch is required"):
        report_finding(ctx, category="CODE_BUG", confidence=0.85, root_cause="x")


def test_data_anomaly_requires_hypothesis(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="data_hypothesis"):
        report_finding(ctx, category="DATA_ANOMALY", confidence=0.8, root_cause="x")


def test_data_anomaly_with_full_fields(ctx: ToolContext) -> None:
    result = report_finding(
        ctx, category="DATA_ANOMALY", confidence=0.82, root_cause="city empty",
        data_hypothesis="city='' for user_id 100~200",
        verification_sql=["SELECT count(*) FROM addresses WHERE city=''"],
        verification_logql=["{service=\"x\"} | json | level=\"ERROR\""],
    )
    assert "recorded" in result.lower()
    assert ctx.findings[0].verification_sql == ["SELECT count(*) FROM addresses WHERE city=''"]


def test_infra_issue_requires_checklist(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="infra_checklist"):
        report_finding(ctx, category="INFRA_ISSUE", confidence=0.7, root_cause="pool")


def test_benign_error_with_patch_and_proposal(ctx: ToolContext) -> None:
    from ai_bot.analyzer.result import Patch
    ctx.patches.append(Patch(file_path="src/main/H.kt", old_content="", new_content="x"))
    result = report_finding(
        ctx, category="BENIGN_ERROR", confidence=0.88,
        root_cause="client disconnect",
        alert_rule_proposal="exception_class!=ClientAbortException",
    )
    assert "recorded" in result.lower()
    assert ctx.findings[0].alert_rule_proposal == "exception_class!=ClientAbortException"


def test_insufficient_context_no_patch_no_extras(ctx: ToolContext) -> None:
    result = report_finding(ctx, category="INSUFFICIENT_CONTEXT", confidence=0.45, root_cause="need cross-service logs")
    assert "recorded" in result.lower()
    assert ctx.findings[0].patch is None


def test_calling_twice_replaces(ctx: ToolContext) -> None:
    report_finding(ctx, category="INSUFFICIENT_CONTEXT", confidence=0.4, root_cause="x")
    report_finding(ctx, category="INSUFFICIENT_CONTEXT", confidence=0.5, root_cause="y")
    assert len(ctx.findings) == 1
    assert ctx.findings[0].confidence == 0.5
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_finding.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: finding 도구 구현**

Create `ai-bot/src/ai_bot/analyzer/tools/finding.py`:

```python
from __future__ import annotations

from typing import Literal

from ai_bot.analyzer.result import AnalysisResult
from ai_bot.analyzer.tools import ToolContext, ToolError


def report_finding(
    ctx: ToolContext,
    *,
    category: Literal["CODE_BUG", "DATA_ANOMALY", "INFRA_ISSUE", "INSUFFICIENT_CONTEXT", "BENIGN_ERROR"],
    confidence: float,
    root_cause: str,
    data_hypothesis: str | None = None,
    verification_sql: list[str] | None = None,
    verification_logql: list[str] | None = None,
    infra_checklist: list[str] | None = None,
    related_metrics: list[str] | None = None,
    alert_rule_proposal: str | None = None,
) -> str:
    """Final reporting tool. Must be called exactly once at the end of analysis.

    Field requirements by category:
      - CODE_BUG: propose_patch must have been called (at least one patch in context)
      - DATA_ANOMALY: data_hypothesis required; verification_sql/logql encouraged
      - INFRA_ISSUE: infra_checklist required
      - BENIGN_ERROR: propose_patch + alert_rule_proposal encouraged
      - INSUFFICIENT_CONTEXT: just root_cause
    """
    if not 0.0 <= confidence <= 1.0:
        raise ToolError("confidence must be in [0.0, 1.0]")

    patch = ctx.patches[-1] if ctx.patches else None

    if category == "CODE_BUG" and patch is None:
        raise ToolError("CODE_BUG: patch is required (call propose_patch first)")
    if category == "DATA_ANOMALY" and not data_hypothesis:
        raise ToolError("DATA_ANOMALY: data_hypothesis is required")
    if category == "INFRA_ISSUE" and not infra_checklist:
        raise ToolError("INFRA_ISSUE: infra_checklist is required")

    result = AnalysisResult(
        category=category,
        confidence=confidence,
        root_cause=root_cause,
        patch=patch if category in ("CODE_BUG", "BENIGN_ERROR") else None,
        data_hypothesis=data_hypothesis,
        verification_sql=verification_sql or [],
        verification_logql=verification_logql or [],
        infra_checklist=infra_checklist or [],
        related_metrics=related_metrics or [],
        alert_rule_proposal=alert_rule_proposal,
    )
    ctx.findings.clear()
    ctx.findings.append(result)
    return f"finding recorded: category={category}, confidence={confidence:.2f}"
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_tools_finding.py -v
```

Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/analyzer/tools/finding.py \
        ai-bot/tests/unit/test_tools_finding.py
git commit -m "feat(tools): report_finding with per-category required-field validation"
```

---

## Task 8: System prompt

**Files:**
- Create: `ai-bot/src/ai_bot/analyzer/prompts.py`

System prompt는 Claude에게 "어떤 카테고리로 분류할지", "어떤 도구를 어떤 순서로 쓸지", "안전 가이드" 등을 가르친다.

- [ ] **Step 1: prompts.py 작성**

Create `ai-bot/src/ai_bot/analyzer/prompts.py`:

```python
SYSTEM_PROMPT = """You are an AI Incident Bot analyzing a production error.

# Your job
Given an error (class, log lines, deployed commit SHA) and access to the deployed source code,
1. Investigate the root cause using the provided tools.
2. Classify the root cause into ONE of these categories.
3. Call `report_finding` exactly once at the end with your conclusion.

# Categories (choose exactly one)

## CODE_BUG
The business logic has a defect. A small, local code change fixes it.
Examples: missing null check, off-by-one, missing validation, wrong condition.
- You MUST call `propose_patch` first with a single-file, ≤30-line change.
- Then call `report_finding(category="CODE_BUG", confidence, root_cause)`.

## BENIGN_ERROR
The error is a normal external condition that doesn't indicate a bug.
Examples: ClientAbortException (client disconnected), AsyncRequestTimeoutException, broken pipe during streaming.
Business logic is fine; the noise is the problem.
- Call `propose_patch` to add a `@ControllerAdvice` ExceptionHandler that downgrades log level OR ignores gracefully.
- Then call `report_finding(category="BENIGN_ERROR", confidence, root_cause, alert_rule_proposal="...")`.
- The `alert_rule_proposal` should be a LogQL fragment suggesting to exclude this exception class from alert rules.

## DATA_ANOMALY
Code paths look correct, but the input/stored data is malformed.
Examples: NULL/empty fields, orphan foreign keys, legacy enum values left in the database.
A code patch wouldn't fix the real problem (and might hide it).
- DO NOT call `propose_patch`.
- Use `read_db_schema` to confirm the table structure.
- Call `report_finding(category="DATA_ANOMALY", confidence, root_cause, data_hypothesis, verification_sql=[...3 queries], verification_logql=[...2 queries])`.
- Verification queries should help a human confirm the hypothesis safely (read-replica-safe SQL).

## INFRA_ISSUE
The error is caused by environment/infrastructure, not application code.
Examples: SQLTransientConnectionException (DB pool exhaustion), socket timeouts to external APIs, OOM.
- DO NOT call `propose_patch`.
- Call `report_finding(category="INFRA_ISSUE", confidence, root_cause, infra_checklist=[...items to verify], related_metrics=[...LogQL queries])`.

## INSUFFICIENT_CONTEXT
You looked but couldn't determine the cause from available code and logs.
Examples: distributed transaction across services, race condition needing cross-service traces.
- DO NOT call `propose_patch`.
- Use confidence < 0.7 to signal uncertainty.
- Call `report_finding(category="INSUFFICIENT_CONTEXT", confidence, root_cause)` with a description of what additional info is needed.

# Investigation workflow (suggested)
1. `read_file` the file:line from the stack trace (if any).
2. `grep` for symbols referenced in the failing code.
3. `git_log` on the file to see recent changes.
4. If DB-related: `read_db_schema` (optionally filtered by suspected table).
5. Decide category. Make patch (if applicable) via `propose_patch`. Then `report_finding`.

# Hard rules
- Call `report_finding` EXACTLY ONCE. Calling it twice replaces the first.
- Patches must be ≤30 lines and in a single file.
- Confidence: 0.0–1.0. Use < 0.7 to mean "I'm not sure, prefer human review".
- All file paths are RELATIVE to the worktree root. Allowlist: `src/main/`, `src/test/`, `src/main/resources/db/migration/`.
- Don't speculate beyond the evidence. If logs don't show the root cause, prefer INSUFFICIENT_CONTEXT.
- For BENIGN_ERROR: only choose this if the error is clearly a normal external condition. If the server might actually be slow/broken, choose INFRA_ISSUE instead.

# What you'll be given
- error_class (e.g. NullPointerException)
- commit_sha (the deployed SHA — worktree is checked out at this revision)
- recent_log_lines (parsed JSON from Loki)
- worktree path (your filesystem context, accessible via the tools)
"""


def build_user_prompt(
    *, error_class: str, commit_sha: str, log_lines: list, worktree_path
) -> str:
    log_summary = "\n".join(
        f"- [{ll.level}] {ll.exception_class or '?'}: {ll.message[:200]} (request_id={ll.request_id})"
        for ll in log_lines[:20]
    ) or "(no logs available)"

    return f"""# Incident
- error_class: {error_class}
- commit_sha: {commit_sha}
- worktree: {worktree_path}

# Recent log lines (most recent first, up to 20)
{log_summary}

Investigate and call report_finding exactly once.
"""
```

- [ ] **Step 2: import smoke test**

Run:
```bash
cd ai-bot
uv run python -c "from ai_bot.analyzer.prompts import SYSTEM_PROMPT, build_user_prompt; print(len(SYSTEM_PROMPT), 'chars')"
```

Expected: ~2000+ chars

- [ ] **Step 3: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/analyzer/prompts.py
git commit -m "feat(analyzer): system prompt with category guides + tool workflow"
```

---

## Task 9: ClaudeAnalyzer (Agent SDK 루프)

**Files:**
- Create: `ai-bot/src/ai_bot/analyzer/claude.py`
- Create: `ai-bot/tests/integration/test_claude_analyzer.py` (실제 API 호출, optional)

Claude Agent SDK Python (`claude_agent_sdk`)의 in-process tool API를 사용한다.

> **API 참고**: `claude-agent-sdk`는 Claude Code CLI를 spawn한다. 도구는 `@tool` 데코레이터 또는 dict로 등록. 정확한 API는 패키지 버전에 따라 다르므로 구현 시 `uv run python -c "import claude_agent_sdk; help(claude_agent_sdk)"`로 확인.

- [ ] **Step 1: ClaudeAnalyzer 구현**

Create `ai-bot/src/ai_bot/analyzer/claude.py`:

```python
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query, tool

from ai_bot.analyzer.prompts import SYSTEM_PROMPT, build_user_prompt
from ai_bot.analyzer.result import AnalysisResult
from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.db_schema import read_db_schema as _read_db_schema
from ai_bot.analyzer.tools.filesystem import grep as _grep
from ai_bot.analyzer.tools.filesystem import read_file as _read_file
from ai_bot.analyzer.tools.finding import report_finding as _report_finding
from ai_bot.analyzer.tools.git_history import git_diff as _git_diff
from ai_bot.analyzer.tools.git_history import git_log as _git_log
from ai_bot.analyzer.tools.patch import propose_patch as _propose_patch

logger = logging.getLogger(__name__)


class ClaudeAnalyzerError(Exception):
    pass


class ClaudeAnalyzer:
    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        max_turns: int = 20,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._model = model
        self._max_turns = max_turns
        self._timeout = timeout_seconds

    async def analyze(
        self,
        *,
        worktree_path: Path,
        error_class: str,
        commit_sha: str,
        log_lines: list,
    ) -> AnalysisResult:
        ctx = ToolContext(worktree_path=worktree_path)

        def _bind(fn):
            """Bind ToolContext into the tool callable for SDK exposure."""
            async def wrapper(**kwargs):
                try:
                    out = fn(ctx, **kwargs)
                    return out
                except ToolError as exc:
                    # 도구 실패는 Claude에게 전달 (호출 다시 시도하도록)
                    return f"ERROR: {exc}"
            wrapper.__name__ = fn.__name__
            return wrapper

        tools_list = [
            tool("read_file", "Read a file from worktree. Allowed dirs: src/main, src/test, src/main/resources/db/migration", _bind(_read_file)),
            tool("grep", "Regex search files under a path_prefix in the worktree.", _bind(_grep)),
            tool("git_log", "Show recent commits, optionally limited to a file. Default limit 10.", _bind(_git_log)),
            tool("git_diff", "Show diff between two revisions (base..head), optionally for a single file.", _bind(_git_diff)),
            tool("read_db_schema", "Read Flyway migration files. Optional `table` filter (keyword).", _bind(_read_db_schema)),
            tool("propose_patch", "Register a single-file patch (≤30 lines). Required before report_finding for CODE_BUG/BENIGN_ERROR.", _bind(_propose_patch)),
            tool("report_finding", "Final reporting. Call EXACTLY ONCE at end.", _bind(_report_finding)),
        ]

        options = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            model=self._model,
            allowed_tools=[t.name for t in tools_list],
            tools=tools_list,
            max_turns=self._max_turns,
        )

        user_prompt = build_user_prompt(
            error_class=error_class, commit_sha=commit_sha,
            log_lines=log_lines, worktree_path=worktree_path,
        )

        start = time.monotonic()
        input_tokens = 0
        output_tokens = 0
        tool_calls = 0
        cost_usd = 0.0

        try:
            async with asyncio.timeout(self._timeout):
                async for message in query(prompt=user_prompt, options=options):
                    # 메시지 종류별 메타데이터 수집
                    meta = getattr(message, "usage", None)
                    if meta:
                        input_tokens += getattr(meta, "input_tokens", 0) or 0
                        output_tokens += getattr(meta, "output_tokens", 0) or 0
                        cost_usd += float(getattr(meta, "cost_usd", 0.0) or 0.0)
                    if getattr(message, "type", None) == "tool_use":
                        tool_calls += 1
        except asyncio.TimeoutError:
            raise ClaudeAnalyzerError(f"analysis timed out after {self._timeout}s") from None

        latency_ms = int((time.monotonic() - start) * 1000)

        if not ctx.findings:
            raise ClaudeAnalyzerError(
                "Claude did not call report_finding. Increase max_turns or check prompt."
            )

        result = ctx.findings[-1]
        # 메타데이터 채우기
        return result.model_copy(update={
            "model": self._model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "tool_calls_count": tool_calls,
            "latency_ms": latency_ms,
        })
```

> **주의**: `claude_agent_sdk`의 정확한 API (특히 `tool()` 헬퍼, `ClaudeAgentOptions`, `query()` 시그니처)는 SDK 버전에 따라 다를 수 있다. 구현 시 다음으로 확인:
>
> ```bash
> uv run python -c "import claude_agent_sdk; print(dir(claude_agent_sdk))"
> ```
>
> 만약 `tool()` helper가 없다면 MCP 서버 패턴으로 전환 (Plan 3 외 영역).

- [ ] **Step 2: 통합 테스트 (optional, 실제 API 호출 — `RUN_REAL_LLM=1`로 enable)**

Create `ai-bot/tests/integration/test_claude_analyzer.py`:

```python
import os
import subprocess
from pathlib import Path

import pytest

from ai_bot.analyzer.claude import ClaudeAnalyzer


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REAL_LLM") != "1",
    reason="실제 Claude API 호출. RUN_REAL_LLM=1로 enable",
)


@pytest.fixture
def buggy_worktree(tmp_path: Path) -> Path:
    """간단한 NPE 시나리오 — Foo.kt에서 null이 될 수 있는 변수 사용"""
    src = tmp_path / "src/main/kotlin"
    src.mkdir(parents=True)
    (src / "Foo.kt").write_text(
        "class Foo {\n"
        "    fun process(input: String?): Int {\n"
        "        return input.length\n"  # NPE: input이 null일 수 있음
        "    }\n"
        "}\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.mark.asyncio
async def test_simple_npe_classified_as_code_bug(buggy_worktree: Path) -> None:
    from ai_bot.services.log_fetcher import LogLine

    logs = [
        LogLine(
            timestamp_ns=1_000_000,
            message="NPE at Foo.process",
            level="ERROR",
            exception_class="NullPointerException",
            request_id="r-1",
            raw={"endpoint": "/api/x"},
        )
    ]
    analyzer = ClaudeAnalyzer()
    result = await analyzer.analyze(
        worktree_path=buggy_worktree,
        error_class="NullPointerException",
        commit_sha="HEAD",
        log_lines=logs,
    )
    assert result.category in {"CODE_BUG", "INSUFFICIENT_CONTEXT"}
    if result.category == "CODE_BUG":
        assert result.patch is not None
        assert "Foo.kt" in result.patch.file_path
```

- [ ] **Step 3: 단위 테스트만 먼저 실행 (real test는 skip됨)**

Run:
```bash
cd ai-bot
uv run pytest tests/integration/test_claude_analyzer.py -v
```

Expected: SKIPPED (RUN_REAL_LLM 미설정)

- [ ] **Step 4: (Optional) 실제 API 1회 검증**

```bash
cd ai-bot
RUN_REAL_LLM=1 ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
uv run pytest tests/integration/test_claude_analyzer.py -v -s
```

Expected: 1~2분 후 PASS 또는 SKIPPED. 비용 ~$0.30.

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/analyzer/claude.py \
        ai-bot/tests/integration/test_claude_analyzer.py
git commit -m "feat(analyzer): ClaudeAnalyzer with Agent SDK + 7 tools registered"
```

---

## Task 10: GitHubClient — Issue 생성

**Files:**
- Create: `ai-bot/src/ai_bot/services/github_client.py`
- Create: `ai-bot/tests/unit/test_github_client.py`

PyGithub은 sync API라 `asyncio.to_thread`로 래핑.

- [ ] **Step 1: 실패하는 테스트 작성 (PyGithub mock)**

Create `ai-bot/tests/unit/test_github_client.py`:

```python
from unittest.mock import MagicMock

import pytest

from ai_bot.services.github_client import GitHubClient


@pytest.fixture
def mock_github(mocker) -> MagicMock:
    fake_gh = MagicMock()
    fake_repo = MagicMock()
    fake_repo.full_name = "kiekk/demo-buggy-service"
    fake_issue = MagicMock()
    fake_issue.number = 42
    fake_issue.html_url = "https://github.com/kiekk/demo-buggy-service/issues/42"
    fake_repo.create_issue.return_value = fake_issue
    fake_gh.get_repo.return_value = fake_repo

    mocker.patch("ai_bot.services.github_client.Github", return_value=fake_gh)
    return fake_gh


@pytest.mark.asyncio
async def test_create_issue_returns_number_and_url(mock_github: MagicMock) -> None:
    client = GitHubClient(token="ghp_fake", repo_full_name="kiekk/demo-buggy-service")
    result = await client.create_issue(
        title="[AI] NPE in Foo",
        body="something",
        labels=["ai-incident", "needs-human-review"],
    )
    assert result.number == 42
    assert result.url == "https://github.com/kiekk/demo-buggy-service/issues/42"

    fake_repo = mock_github.get_repo.return_value
    fake_repo.create_issue.assert_called_once_with(
        title="[AI] NPE in Foo",
        body="something",
        labels=["ai-incident", "needs-human-review"],
    )


@pytest.mark.asyncio
async def test_create_issue_dry_run_does_not_call_github(mocker) -> None:
    mock_gh_cls = mocker.patch("ai_bot.services.github_client.Github")
    client = GitHubClient(token="ghp_fake", repo_full_name="x/y", dry_run=True)
    result = await client.create_issue(title="x", body="x", labels=[])
    assert result.number == 0
    mock_gh_cls.return_value.get_repo.assert_not_called()
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_github_client.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: GitHubClient (Issue) 구현**

Create `ai-bot/src/ai_bot/services/github_client.py`:

```python
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from github import Github

logger = logging.getLogger(__name__)


@dataclass
class IssueRef:
    number: int
    url: str


@dataclass
class PullRequestRef:
    number: int
    url: str
    branch: str


class GitHubClient:
    def __init__(
        self,
        *,
        token: str,
        repo_full_name: str,
        dry_run: bool = False,
    ) -> None:
        self._token = token
        self._repo_full_name = repo_full_name
        self._dry_run = dry_run

    async def create_issue(self, *, title: str, body: str, labels: list[str]) -> IssueRef:
        if self._dry_run:
            logger.info("[DRY_RUN] github create_issue: title=%s", title)
            return IssueRef(number=0, url=f"[dry-run]/{self._repo_full_name}/issues/0")

        def _sync() -> IssueRef:
            gh = Github(self._token)
            repo = gh.get_repo(self._repo_full_name)
            issue = repo.create_issue(title=title, body=body, labels=labels)
            return IssueRef(number=issue.number, url=issue.html_url)

        return await asyncio.to_thread(_sync)
```

- [ ] **Step 4: pytest-mock fixture 사용을 위해 dev deps에 추가 (이미 있음)**

Run:
```bash
cd ai-bot
uv sync
uv run pytest tests/unit/test_github_client.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/services/github_client.py \
        ai-bot/tests/unit/test_github_client.py
git commit -m "feat(services): GitHubClient.create_issue with dry_run"
```

---

## Task 11: GitHubClient — Branch + Patch + Draft PR

**Files:**
- Modify: `ai-bot/src/ai_bot/services/github_client.py`
- Modify: `ai-bot/tests/unit/test_github_client.py`

PR 생성 흐름:
1. 새 브랜치 생성 (`ai-fix/issue-{n}`)
2. 패치 파일 commit (PyGithub `update_file`)
3. Draft PR 생성 + 라벨 + `Fixes #N` 본문

- [ ] **Step 1: 테스트 추가 — create_pull_request_with_patch**

`ai-bot/tests/unit/test_github_client.py`에 다음 테스트 추가:

```python
@pytest.fixture
def mock_github_with_pr(mocker) -> MagicMock:
    fake_gh = MagicMock()
    fake_repo = MagicMock()
    fake_repo.full_name = "kiekk/demo-buggy-service"
    fake_repo.default_branch = "main"

    # base SHA
    fake_main_ref = MagicMock()
    fake_main_ref.object.sha = "main-sha"
    fake_repo.get_git_ref.return_value = fake_main_ref

    # get existing file
    fake_existing_file = MagicMock()
    fake_existing_file.path = "src/main/kotlin/Foo.kt"
    fake_existing_file.sha = "file-sha-1"
    fake_existing_file.decoded_content = b"fun bar() {}\n"
    fake_repo.get_contents.return_value = fake_existing_file

    # update_file
    fake_repo.update_file.return_value = {"commit": MagicMock(sha="commit-sha")}

    # create_pull
    fake_pr = MagicMock()
    fake_pr.number = 99
    fake_pr.html_url = "https://github.com/kiekk/demo-buggy-service/pull/99"
    fake_repo.create_pull.return_value = fake_pr

    # add labels: PR도 issue처럼 add_to_labels
    fake_pr.add_to_labels = MagicMock()

    fake_gh.get_repo.return_value = fake_repo
    mocker.patch("ai_bot.services.github_client.Github", return_value=fake_gh)
    return fake_gh


@pytest.mark.asyncio
async def test_create_pull_request_with_patch(mock_github_with_pr: MagicMock) -> None:
    from ai_bot.analyzer.result import Patch

    client = GitHubClient(token="ghp_fake", repo_full_name="kiekk/demo-buggy-service")
    pr = await client.create_pull_request_with_patch(
        issue_number=42,
        branch="ai-fix/issue-42",
        title="[AI Fix] #42 - NPE",
        body="fixes NPE",
        labels=["noise-reduction", "human-review-required"],
        patch=Patch(
            file_path="src/main/kotlin/Foo.kt",
            old_content="fun bar() {}\n",
            new_content="fun bar(): Int = 0\n",
        ),
        base_branch="main",
        commit_message="fix: add return value (Fixes #42)",
    )
    assert pr.number == 99
    assert pr.branch == "ai-fix/issue-42"
    assert "pull/99" in pr.url

    fake_repo = mock_github_with_pr.get_repo.return_value
    fake_repo.create_git_ref.assert_called_once_with(ref="refs/heads/ai-fix/issue-42", sha="main-sha")
    fake_repo.update_file.assert_called_once()
    fake_repo.create_pull.assert_called_once()
    create_pull_kwargs = fake_repo.create_pull.call_args.kwargs
    assert create_pull_kwargs["draft"] is True
    assert create_pull_kwargs["base"] == "main"
    assert create_pull_kwargs["head"] == "ai-fix/issue-42"
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_github_client.py::test_create_pull_request_with_patch -v
```

Expected: FAIL — `AttributeError` (method 없음)

- [ ] **Step 3: create_pull_request_with_patch 구현**

`ai-bot/src/ai_bot/services/github_client.py`의 `GitHubClient` 클래스에 다음 메서드 추가 (`create_issue` 아래에):

```python
    async def create_pull_request_with_patch(
        self,
        *,
        issue_number: int,
        branch: str,
        title: str,
        body: str,
        labels: list[str],
        patch,  # ai_bot.analyzer.result.Patch
        base_branch: str = "main",
        commit_message: str,
    ) -> PullRequestRef:
        if self._dry_run:
            logger.info("[DRY_RUN] github create_pr: branch=%s title=%s", branch, title)
            return PullRequestRef(number=0, branch=branch, url=f"[dry-run]/{self._repo_full_name}/pull/0")

        def _sync() -> PullRequestRef:
            gh = Github(self._token)
            repo = gh.get_repo(self._repo_full_name)

            # 1. base branch SHA 가져오기
            base_ref = repo.get_git_ref(f"heads/{base_branch}")
            base_sha = base_ref.object.sha

            # 2. 새 브랜치 생성
            try:
                repo.create_git_ref(ref=f"refs/heads/{branch}", sha=base_sha)
            except Exception as exc:  # 이미 존재해도 진행
                logger.warning("create_git_ref %s: %s — using existing", branch, exc)

            # 3. 파일 업데이트 (patch.file_path를 base_branch에서 읽고 sha 받아서 update)
            existing = repo.get_contents(patch.file_path, ref=branch)
            repo.update_file(
                path=patch.file_path,
                message=commit_message,
                content=patch.new_content,
                sha=existing.sha,
                branch=branch,
            )

            # 4. Draft PR 생성
            pr = repo.create_pull(
                title=title,
                body=body,
                base=base_branch,
                head=branch,
                draft=True,
            )

            # 5. 라벨 추가
            if labels:
                pr.add_to_labels(*labels)

            return PullRequestRef(number=pr.number, branch=branch, url=pr.html_url)

        return await asyncio.to_thread(_sync)
```

- [ ] **Step 4: 테스트 재실행 (전체 GitHubClient 테스트)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_github_client.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/services/github_client.py \
        ai-bot/tests/unit/test_github_client.py
git commit -m "feat(services): GitHubClient.create_pull_request_with_patch (Draft + labels)"
```

---

## Task 12: PR/Issue 본문 템플릿

**Files:**
- Create: `ai-bot/src/ai_bot/services/pr_templates.py`
- Create: `ai-bot/tests/unit/test_pr_templates.py`

각 카테고리별 본문 + Slack 메시지 생성 함수.

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_pr_templates.py`:

```python
from ai_bot.analyzer.result import AnalysisResult, Patch
from ai_bot.services.pr_templates import (
    build_code_bug_issue_body,
    build_code_bug_pr_body,
    build_data_anomaly_issue_body,
    build_infra_issue_body,
    build_benign_pr_body,
    build_benign_alert_proposal_body,
    build_insufficient_context_issue_body,
    build_slack_message,
)


def _result(category, **overrides) -> AnalysisResult:
    base = {
        "category": category,
        "confidence": 0.85,
        "root_cause": "test root cause",
        "model": "claude-sonnet-4-6",
        "cost_usd": 0.5,
        "tool_calls_count": 10,
        "latency_ms": 30000,
    }
    base.update(overrides)
    return AnalysisResult(**base)


def test_code_bug_issue_body_includes_metadata() -> None:
    body = build_code_bug_issue_body(
        result=_result("CODE_BUG", patch=Patch(file_path="src/main/x.kt", old_content="a", new_content="b")),
        service="demo-buggy-service",
        commit_sha="abc123def",
        run_id="run-1",
    )
    assert "demo-buggy-service" in body
    assert "abc123de" in body  # short sha
    assert "test root cause" in body
    assert "ai-bot" in body or "AI" in body


def test_code_bug_pr_body_mentions_review_warning_and_issue_link() -> None:
    body = build_code_bug_pr_body(
        result=_result("CODE_BUG", patch=Patch(file_path="src/main/x.kt", old_content="a", new_content="b")),
        issue_number=42,
        run_id="run-1",
    )
    assert "Fixes #42" in body
    assert "Review carefully" in body or "review" in body.lower()


def test_data_anomaly_body_includes_sql_and_logql() -> None:
    body = build_data_anomaly_issue_body(
        result=_result(
            "DATA_ANOMALY",
            data_hypothesis="city='' for user_id 100..200",
            verification_sql=["SELECT count(*) FROM addresses WHERE city=''"],
            verification_logql=["{service=\"x\"} | json"],
        ),
        service="demo-buggy-service",
        commit_sha="abc123",
        run_id="run-1",
    )
    assert "city=''" in body
    assert "```sql" in body
    assert "```logql" in body
    assert "코드 PR을 자동 생성하지 않았습니다" in body or "no PR" in body.lower() or "PR was not" in body


def test_infra_issue_body_includes_checklist() -> None:
    body = build_infra_issue_body(
        result=_result("INFRA_ISSUE", infra_checklist=["check HikariCP", "check RDS connections"], related_metrics=["{service=\"x\"} | rate"]),
        service="demo-buggy-service",
        commit_sha="abc123",
        run_id="run-1",
    )
    assert "check HikariCP" in body
    assert "check RDS connections" in body


def test_benign_pr_body_mentions_noise() -> None:
    body = build_benign_pr_body(
        result=_result("BENIGN_ERROR", patch=Patch(file_path="src/main/H.kt", old_content="", new_content="x")),
        issue_number=99,
        run_id="run-2",
    )
    assert "noise" in body.lower() or "BENIGN" in body
    assert "Fixes #99" in body


def test_benign_alert_proposal_body() -> None:
    body = build_benign_alert_proposal_body(
        result=_result("BENIGN_ERROR", alert_rule_proposal="exception_class!=ClientAbortException", patch=Patch(file_path="x", old_content="", new_content="")),
        related_pr_number=99,
        run_id="run-2",
    )
    assert "exception_class!=ClientAbortException" in body
    assert "PR #99" in body
    assert "자동 수정하지 않습니다" in body or "do not auto" in body.lower() or "not automatically" in body.lower()


def test_insufficient_context_body() -> None:
    body = build_insufficient_context_issue_body(
        result=_result("INSUFFICIENT_CONTEXT", confidence=0.45),
        service="x", commit_sha="abc", run_id="r",
    )
    assert "0.45" in body or "0.4" in body


def test_slack_message_for_code_bug() -> None:
    msg = build_slack_message(
        category="CODE_BUG",
        issue_url="https://github.com/x/y/issues/42",
        pr_url="https://github.com/x/y/pull/43",
        confidence=0.85,
        cost_usd=0.42,
        latency_ms=135000,
        short_root_cause="NPE in Foo",
    )
    assert "✅" in msg
    assert "pull/43" in msg
    assert "0.85" in msg


def test_slack_message_for_data_anomaly() -> None:
    msg = build_slack_message(
        category="DATA_ANOMALY",
        issue_url="https://github.com/x/y/issues/14",
        pr_url=None,
        confidence=0.82,
        cost_usd=0.38,
        latency_ms=120000,
        short_root_cause="addresses.city empty",
    )
    assert "🔎" in msg
    assert "issues/14" in msg
    assert "pull" not in msg.split("issues/14")[1].split("\n")[0]  # PR 링크 없음


def test_slack_message_for_benign_error() -> None:
    msg = build_slack_message(
        category="BENIGN_ERROR",
        issue_url="https://github.com/x/y/issues/15",
        pr_url="https://github.com/x/y/pull/16",
        confidence=0.88,
        cost_usd=0.3,
        latency_ms=90000,
        short_root_cause="ClientAbortException",
    )
    assert "🔇" in msg
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_pr_templates.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: 본문 템플릿 구현**

Create `ai-bot/src/ai_bot/services/pr_templates.py`:

```python
from __future__ import annotations

from textwrap import dedent

from ai_bot.analyzer.result import AnalysisResult


def _meta_footer(run_id: str, result: AnalysisResult) -> str:
    return (
        f"\n\n---\n"
        f"🤖 ai-bot (model={result.model}, confidence={result.confidence:.2f}, "
        f"category={result.category})\n"
        f"Run: `{run_id}` | Cost: ${result.cost_usd:.3f} | Tool calls: {result.tool_calls_count}\n"
    )


def build_code_bug_issue_body(
    *, result: AnalysisResult, service: str, commit_sha: str, run_id: str,
) -> str:
    return dedent(f"""\
        ## 🐛 코드 버그 — 자동 PR 생성됨

        **서비스**: {service} @ `{commit_sha[:8]}`
        **카테고리**: CODE_BUG (confidence: {result.confidence:.2f})

        ### 추정 원인
        {result.root_cause}

        AI 봇이 자동으로 패치 PR을 생성했습니다. 본 Issue와 연결됩니다.
        """) + _meta_footer(run_id, result)


def build_code_bug_pr_body(
    *, result: AnalysisResult, issue_number: int, run_id: str,
) -> str:
    return dedent(f"""\
        ## 🤖 AI 자동 생성 PR

        > ⚠️ This PR was generated by AI. Review carefully before merging.

        Fixes #{issue_number}

        ### 추정 원인
        {result.root_cause}

        ### 머지 전 확인 사항
        - [ ] 패치가 실제 root cause를 해결하는지 (증상 완화만이 아닌지)
        - [ ] 기존 테스트가 깨지지 않는지 (CI 통과 확인)
        - [ ] 패치 범위가 적절한지 (다른 곳에도 같은 버그가 있는지)
        """) + _meta_footer(run_id, result)


def build_data_anomaly_issue_body(
    *, result: AnalysisResult, service: str, commit_sha: str, run_id: str,
) -> str:
    sql_block = "\n\n".join(f"```sql\n{q}\n```" for q in result.verification_sql) or "(none)"
    logql_block = "\n\n".join(f"```logql\n{q}\n```" for q in result.verification_logql) or "(none)"

    return dedent(f"""\
        ## 🔎 데이터 이상 추정 — 코드 수정 불필요

        **서비스**: {service} @ `{commit_sha[:8]}`
        **카테고리**: DATA_ANOMALY (confidence: {result.confidence:.2f})

        ### 가설
        {result.data_hypothesis}

        ### 추정 원인
        {result.root_cause}

        ### ✅ 검증 SQL (운영 read-replica 권장)

        {sql_block}

        ### ✅ 검증 LogQL

        {logql_block}

        ### ⚠️ 이 Issue는 코드 PR을 자동 생성하지 않았습니다
        AI 분석 결과 코드 로직 자체에는 명백한 결함이 보이지 않습니다.
        잘못된 코드 패치는 진짜 원인(데이터 정합성)을 가릴 수 있어
        사람의 판단을 요청드립니다.
        """) + _meta_footer(run_id, result)


def build_infra_issue_body(
    *, result: AnalysisResult, service: str, commit_sha: str, run_id: str,
) -> str:
    checklist = "\n".join(f"- [ ] {item}" for item in result.infra_checklist) or "- [ ] (none provided)"
    metrics = "\n\n".join(f"```logql\n{m}\n```" for m in result.related_metrics) or "(none)"

    return dedent(f"""\
        ## ⚙️ 인프라 이슈 추정 — 코드 수정 불필요

        **서비스**: {service} @ `{commit_sha[:8]}`
        **카테고리**: INFRA_ISSUE (confidence: {result.confidence:.2f})

        ### 추정 원인
        {result.root_cause}

        ### ✅ 점검 체크리스트
        {checklist}

        ### 관련 메트릭/쿼리

        {metrics}
        """) + _meta_footer(run_id, result)


def build_benign_pr_body(
    *, result: AnalysisResult, issue_number: int, run_id: str,
) -> str:
    return dedent(f"""\
        ## 🔇 노이즈 에러 처리

        > ⚠️ This PR was generated by AI. Review carefully before merging.

        Fixes #{issue_number}

        **카테고리**: BENIGN_ERROR (confidence: {result.confidence:.2f})

        ### 무엇을 바꿨나
        에러가 외부의 정상적 조건(클라이언트 disconnect 등)에 대한 반응이라
        ExceptionHandler를 추가해 ERROR 대신 INFO 레벨로 로깅합니다.

        ### 추정 원인
        {result.root_cause}

        ### 머지 전 확인 사항
        - [ ] 이 예외가 정말 클라이언트/외부 원인인지 (서버가 느려서가 아닌지)
        - [ ] 다른 endpoint에서도 같은 패턴이 있는지
        - [ ] 연결된 Issue의 alert rule 조정 제안 검토
        """) + _meta_footer(run_id, result)


def build_benign_alert_proposal_body(
    *, result: AnalysisResult, related_pr_number: int, run_id: str,
) -> str:
    proposal = result.alert_rule_proposal or "(no specific proposal)"
    return dedent(f"""\
        ## 🔇 노이즈 에러 추정 — 알림 규칙 조정 제안

        관련 PR #{related_pr_number}에서 ExceptionHandler를 추가했습니다.
        추가로 다음 알림 규칙 조정을 권장하지만, **AI는 alert rule을
        자동 수정하지 않습니다**. 사람이 검증 후 수동 적용해주세요.

        ### 조정 제안 (수동 적용)

        ```yaml
        # infra/grafana/provisioning/alerting/alerts.yaml
        - title: AI Bot - High Error Log Rate
          query: |
            sum by (commit_sha, service) (
              count_over_time({{job="spring-boot-demo"}} | json
                | level="ERROR"
                | {proposal}
                [5m])
            )
        ```

        ### ⚠️ 적용 전 체크리스트
        - [ ] 이 예외가 전체 ERROR의 다수를 차지하는지 (LogQL로 확인)
        - [ ] 정말 클라이언트 측 원인인지 (서버 측 성능 문제로 클라이언트가 포기한 게 아닌지)
        - [ ] 다른 운영자의 검토 (이 조정으로 진짜 인시던트를 놓칠 위험)
        """) + _meta_footer(run_id, result)


def build_insufficient_context_issue_body(
    *, result: AnalysisResult, service: str, commit_sha: str, run_id: str,
) -> str:
    return dedent(f"""\
        ## ⚠️ 분석 불가 — 추가 컨텍스트 필요

        **서비스**: {service} @ `{commit_sha[:8]}`
        **카테고리**: INSUFFICIENT_CONTEXT (confidence: {result.confidence:.2f})

        ### AI의 결론
        {result.root_cause}

        ### 권장 다음 단계
        AI가 사용 가능한 정보(스택 트레이스, 로그, 코드)만으로는 원인을 단정할 수
        없습니다. 다음 중 하나가 도움이 될 수 있습니다.

        - 인접 마이크로서비스의 같은 시간대 로그 확인
        - 분산 트레이싱 (Tempo/Jaeger) 확인
        - 인프라 메트릭 (DB, 네트워크) 시계열 확인
        """) + _meta_footer(run_id, result)


def build_slack_message(
    *,
    category: str,
    issue_url: str,
    pr_url: str | None,
    confidence: float,
    cost_usd: float,
    latency_ms: int,
    short_root_cause: str,
) -> str:
    latency_s = latency_ms / 1000
    meta = f"confidence: {confidence:.2f} | ${cost_usd:.3f} | {latency_s:.1f}s"

    if category == "CODE_BUG":
        return (
            f"✅ PR 생성됨 — {short_root_cause}\n"
            f"{meta}\n"
            f"Issue: {issue_url}\n"
            f"PR: {pr_url}"
        )
    if category == "BENIGN_ERROR":
        return (
            f"🔇 노이즈 에러 처리 PR 생성됨 — {short_root_cause}\n"
            f"{meta}\n"
            f"Issue: {issue_url}\n"
            f"PR: {pr_url}"
        )
    if category == "DATA_ANOMALY":
        return (
            f"🔎 데이터 조사 필요 — {short_root_cause}\n"
            f"PR은 생성하지 않았습니다. 검증 쿼리는 Issue 본문 참고.\n"
            f"{meta}\n"
            f"Issue: {issue_url}"
        )
    if category == "INFRA_ISSUE":
        return (
            f"⚙️ 인프라 점검 필요 — {short_root_cause}\n"
            f"{meta}\n"
            f"Issue: {issue_url}"
        )
    if category == "INSUFFICIENT_CONTEXT":
        return (
            f"⚠️ 분석 불가 (추가 컨텍스트 필요) — {short_root_cause}\n"
            f"{meta}\n"
            f"Issue: {issue_url}"
        )
    return f"❓ unknown category {category}: {short_root_cause}\nIssue: {issue_url}"
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_pr_templates.py -v
```

Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/services/pr_templates.py \
        ai-bot/tests/unit/test_pr_templates.py
git commit -m "feat(services): PR/Issue body templates + category-aware Slack message"
```

---

## Task 13: BENIGN_ERROR 24h 차단 (Safety #12)

**Files:**
- Create: `ai-bot/src/ai_bot/safety/benign_cooldown.py`
- Create: `ai-bot/tests/unit/test_benign_cooldown.py`

같은 fingerprint가 24시간 내 BENIGN으로 분류된 적 있으면 다음 발화는 PR을 만들지 않고 기존 Issue에 댓글만 추가 (spec safety #12).

- [ ] **Step 1: 실패하는 테스트 작성**

Create `ai-bot/tests/unit/test_benign_cooldown.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import AnalysisRun, Incident
from ai_bot.safety.benign_cooldown import is_benign_in_cooldown


def _make_incident(fp: str = "fp-1") -> Incident:
    return Incident(
        fingerprint=fp, service="x", commit_sha="c", error_class="E", request_id="r", occurrence_count=1,
    )


@pytest.mark.asyncio
async def test_no_prior_benign_returns_false(db_session: AsyncSession) -> None:
    inc = _make_incident()
    db_session.add(inc)
    await db_session.commit()
    in_cool = await is_benign_in_cooldown(db_session, incident_id=inc.id, hours=24, now=datetime.now(UTC))
    assert in_cool is False


@pytest.mark.asyncio
async def test_recent_benign_returns_true(db_session: AsyncSession) -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    inc = _make_incident()
    db_session.add(inc)
    await db_session.flush()
    db_session.add(AnalysisRun(
        incident_id=inc.id, status="COMPLETED", category="BENIGN_ERROR",
        started_at=now - timedelta(hours=2),
        completed_at=now - timedelta(hours=2),
    ))
    await db_session.commit()
    in_cool = await is_benign_in_cooldown(db_session, incident_id=inc.id, hours=24, now=now)
    assert in_cool is True


@pytest.mark.asyncio
async def test_old_benign_outside_window_returns_false(db_session: AsyncSession) -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    inc = _make_incident()
    db_session.add(inc)
    await db_session.flush()
    db_session.add(AnalysisRun(
        incident_id=inc.id, status="COMPLETED", category="BENIGN_ERROR",
        started_at=now - timedelta(days=2),
        completed_at=now - timedelta(days=2),
    ))
    await db_session.commit()
    in_cool = await is_benign_in_cooldown(db_session, incident_id=inc.id, hours=24, now=now)
    assert in_cool is False


@pytest.mark.asyncio
async def test_recent_codebug_does_not_count(db_session: AsyncSession) -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    inc = _make_incident()
    db_session.add(inc)
    await db_session.flush()
    db_session.add(AnalysisRun(
        incident_id=inc.id, status="COMPLETED", category="CODE_BUG",
        started_at=now - timedelta(hours=1), completed_at=now - timedelta(hours=1),
    ))
    await db_session.commit()
    in_cool = await is_benign_in_cooldown(db_session, incident_id=inc.id, hours=24, now=now)
    assert in_cool is False
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_benign_cooldown.py -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: 구현**

Create `ai-bot/src/ai_bot/safety/benign_cooldown.py`:

```python
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import AnalysisRun


async def is_benign_in_cooldown(
    session: AsyncSession, *, incident_id: int, hours: int, now: datetime,
) -> bool:
    """같은 incident가 hours 내 BENIGN_ERROR로 분류된 적 있는지 확인."""
    threshold = now - timedelta(hours=hours)
    stmt = (
        select(AnalysisRun.id)
        .where(
            AnalysisRun.incident_id == incident_id,
            AnalysisRun.category == "BENIGN_ERROR",
            AnalysisRun.completed_at >= threshold,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
```

- [ ] **Step 4: 테스트 재실행**

Run:
```bash
cd ai-bot
uv run pytest tests/unit/test_benign_cooldown.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/safety/benign_cooldown.py \
        ai-bot/tests/unit/test_benign_cooldown.py
git commit -m "feat(safety): BENIGN_ERROR 24h cooldown check"
```

---

## Task 14: Orchestrator 확장 — PR/Issue 분기

**Files:**
- Modify: `ai-bot/src/ai_bot/orchestrator.py`
- Create: `ai-bot/tests/integration/test_orchestrator_with_github.py`

- [ ] **Step 1: Orchestrator를 GitHubClient 받도록 확장**

`ai-bot/src/ai_bot/orchestrator.py`의 `Orchestrator` 클래스 시그니처/생성자/handle 메서드를 다음으로 교체:

```python
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from ai_bot.analyzer.result import AnalysisResult
from ai_bot.config import Settings
from ai_bot.db.models import AnalysisRun
from ai_bot.safety import benign_cooldown, cost_guard, dedup
from ai_bot.services.github_client import GitHubClient
from ai_bot.services.log_fetcher import LogFetcher, LogLine
from ai_bot.services.pr_templates import (
    build_benign_alert_proposal_body,
    build_benign_pr_body,
    build_code_bug_issue_body,
    build_code_bug_pr_body,
    build_data_anomaly_issue_body,
    build_infra_issue_body,
    build_insufficient_context_issue_body,
    build_slack_message,
)
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
        github: GitHubClient,
    ) -> None:
        self._settings = settings
        self._session_maker = session_maker
        self._log_fetcher = log_fetcher
        self._repo_manager = repo_manager
        self._slack = slack
        self._analyzer = analyzer
        self._github = github

    async def handle(self, event: IncidentEvent) -> None:
        now = datetime.now(UTC)

        async with self._session_maker() as session:
            dedup_result = await dedup.dedup_or_register(
                session, event, window_minutes=self._settings.dedup_window_minutes, now=now,
            )
            if dedup_result.kind == "DUPLICATE":
                await self._slack.post(
                    f"🔁 기존 인시던트 재발 (총 {dedup_result.occurrence_count}회) — "
                    f"{event.service} @ {event.commit_sha[:8]} {event.error_class}"
                )
                return

            allowed = await cost_guard.check_daily_cap(
                session, cap_usd=self._settings.daily_cost_cap_usd, now=now,
            )
            if not allowed:
                await self._slack.post(
                    f"💸 일일 LLM 비용 cap (${self._settings.daily_cost_cap_usd}) 초과 — 분석 거절"
                )
                return

            run = AnalysisRun(incident_id=dedup_result.incident_id, status="ANALYZING", started_at=now)
            session.add(run)
            await session.commit()
            await session.refresh(run)
            run_id = f"run-{run.id}"

            await self._slack.post(
                f"🚨 에러 감지 — {event.service} @ {event.commit_sha[:8]} ({event.error_class})"
            )

            worktree = None
            try:
                logs = await self._log_fetcher.fetch_recent_errors(
                    service=event.service, commit_sha=event.commit_sha,
                    window_minutes=self._settings.log_query_window_minutes,
                )
                worktree = await self._repo_manager.checkout_at_sha(event.commit_sha)
                await self._slack.post(
                    f"🔍 분석 시작 — Claude Agent가 코드 탐색 (로그 {len(logs)}건)"
                )

                start = time.monotonic()
                result = await self._analyzer.analyze(
                    worktree_path=worktree, error_class=event.error_class,
                    commit_sha=event.commit_sha, log_lines=logs,
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                await cost_guard.record_usage(
                    session, run_id=run.id, model=result.model,
                    input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                    cost_usd=result.cost_usd, tool_calls_count=result.tool_calls_count,
                    latency_ms=latency_ms,
                )

                # 카테고리별 분기
                issue_url, pr_url = await self._route_by_category(
                    session=session, event=event, result=result,
                    incident_id=dedup_result.incident_id, run_id=run_id, now=now,
                )

                run.status = "COMPLETED"
                run.category = result.category
                run.confidence = result.confidence
                run.root_cause = result.root_cause
                run.completed_at = datetime.now(UTC)
                await session.commit()

                short = result.root_cause[:120]
                await self._slack.post(build_slack_message(
                    category=result.category, issue_url=issue_url, pr_url=pr_url,
                    confidence=result.confidence, cost_usd=result.cost_usd,
                    latency_ms=latency_ms, short_root_cause=short,
                ))
            except RepoManagerError as exc:
                run.status = "FAILED"
                run.error_message = str(exc)
                run.completed_at = datetime.now(UTC)
                await session.commit()
                await self._slack.post(f"❌ 코드 체크아웃 실패: {event.commit_sha[:8]} ({exc})")
            except Exception as exc:  # noqa: BLE001 — orchestrator safety
                logger.exception("orchestrator error")
                run.status = "FAILED"
                run.error_message = repr(exc)
                run.completed_at = datetime.now(UTC)
                await session.commit()
                await self._slack.post(f"⚠️ 분석 실패: {exc}")
            finally:
                if worktree is not None:
                    await self._repo_manager.cleanup_worktree(worktree)

    async def _route_by_category(
        self,
        *,
        session,
        event: IncidentEvent,
        result: AnalysisResult,
        incident_id: int,
        run_id: str,
        now: datetime,
    ) -> tuple[str, str | None]:
        """카테고리별로 Issue/PR 생성. (issue_url, pr_url_or_None) 반환."""
        category = result.category
        labels_base = ["ai-incident"]

        if category == "CODE_BUG" and result.confidence >= 0.7 and result.patch is not None:
            issue_body = build_code_bug_issue_body(
                result=result, service=event.service,
                commit_sha=event.commit_sha, run_id=run_id,
            )
            issue = await self._github.create_issue(
                title=f"[AI] {event.error_class} in {event.service}",
                body=issue_body,
                labels=labels_base + ["needs-human-review"],
            )
            pr = await self._github.create_pull_request_with_patch(
                issue_number=issue.number,
                branch=f"ai-fix/issue-{issue.number}",
                title=f"[AI Fix] #{issue.number} - {result.root_cause[:60]}",
                body=build_code_bug_pr_body(result=result, issue_number=issue.number, run_id=run_id),
                labels=labels_base + ["human-review-required"],
                patch=result.patch,
                commit_message=f"fix: {result.root_cause[:60]} (Fixes #{issue.number})",
            )
            from ai_bot.db.models import Incident
            await session.execute(
                Incident.__table__.update()
                .where(Incident.id == incident_id)
                .values(github_issue_number=issue.number)
            )
            return issue.url, pr.url

        if category == "BENIGN_ERROR" and result.confidence >= 0.7 and result.patch is not None:
            # 24h 차단 확인
            in_cool = await benign_cooldown.is_benign_in_cooldown(
                session, incident_id=incident_id, hours=24, now=now,
            )
            if in_cool:
                # 재발화: 댓글만, 새 PR 안 만듦. Plan 3 단순화 — Issue만 새로 만들고 PR 안 만듦
                issue = await self._github.create_issue(
                    title=f"[AI] (BENIGN repeat) {event.error_class}",
                    body=f"동일 fingerprint가 24h 내 BENIGN으로 분류됨 (run: {run_id}). 새 PR 생성 안 함.",
                    labels=labels_base + ["noise-reduction", "duplicate"],
                )
                return issue.url, None

            issue_body = (
                f"## 🔇 노이즈 에러\n\n"
                f"**서비스**: {event.service} @ `{event.commit_sha[:8]}`\n\n"
                f"### 추정 원인\n{result.root_cause}\n\n"
                f"자동 PR 생성 + alert rule 조정 제안 Issue 별도 생성됨."
            )
            issue = await self._github.create_issue(
                title=f"[AI] BENIGN {event.error_class}",
                body=issue_body,
                labels=labels_base + ["noise-reduction"],
            )
            pr = await self._github.create_pull_request_with_patch(
                issue_number=issue.number,
                branch=f"ai-fix/issue-{issue.number}",
                title=f"[AI Fix] #{issue.number} - noise reduction: {event.error_class}",
                body=build_benign_pr_body(result=result, issue_number=issue.number, run_id=run_id),
                labels=labels_base + ["noise-reduction", "human-review-required"],
                patch=result.patch,
                commit_message=f"chore: handle {event.error_class} as noise (Fixes #{issue.number})",
            )
            # alert rule 조정 제안 Issue 별도 생성
            await self._github.create_issue(
                title=f"[AI Proposal] alert rule 조정 — {event.error_class}",
                body=build_benign_alert_proposal_body(
                    result=result, related_pr_number=pr.number, run_id=run_id,
                ),
                labels=labels_base + ["noise-reduction", "alert-rule-proposal"],
            )
            return issue.url, pr.url

        if category == "DATA_ANOMALY":
            body = build_data_anomaly_issue_body(
                result=result, service=event.service,
                commit_sha=event.commit_sha, run_id=run_id,
            )
            issue = await self._github.create_issue(
                title=f"[AI] DATA_ANOMALY: {event.error_class} in {event.service}",
                body=body, labels=labels_base + ["data-anomaly", "needs-human-review"],
            )
            return issue.url, None

        if category == "INFRA_ISSUE":
            body = build_infra_issue_body(
                result=result, service=event.service,
                commit_sha=event.commit_sha, run_id=run_id,
            )
            issue = await self._github.create_issue(
                title=f"[AI] INFRA_ISSUE: {event.error_class} in {event.service}",
                body=body, labels=labels_base + ["infra-issue", "needs-human-review"],
            )
            return issue.url, None

        # INSUFFICIENT_CONTEXT 또는 confidence < 0.7
        body = build_insufficient_context_issue_body(
            result=result, service=event.service,
            commit_sha=event.commit_sha, run_id=run_id,
        )
        issue = await self._github.create_issue(
            title=f"[AI] needs review: {event.error_class}",
            body=body, labels=labels_base + ["insufficient-context", "needs-human-review"],
        )
        return issue.url, None
```

- [ ] **Step 2: Orchestrator 통합 테스트 (GitHub mock)**

Create `ai-bot/tests/integration/test_orchestrator_with_github.py`:

```python
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_bot.analyzer.result import AnalysisResult, Patch
from ai_bot.config import Settings
from ai_bot.db.models import Base
from ai_bot.orchestrator import Orchestrator
from ai_bot.services.github_client import GitHubClient, IssueRef, PullRequestRef
from ai_bot.services.log_fetcher import LogFetcher
from ai_bot.services.repo_manager import RepoManager
from ai_bot.services.slack_notifier import SlackNotifier
from ai_bot.webhook.schemas import IncidentEvent


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("GITHUB_REPO", "x/y")
    monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/x/y.git")
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


def _make_orchestrator(settings, session_maker, analyzer_result, *, tmp_path: Path):
    log_fetcher = AsyncMock(spec=LogFetcher)
    log_fetcher.fetch_recent_errors.return_value = []
    repo_manager = AsyncMock(spec=RepoManager)
    repo_manager.checkout_at_sha.return_value = tmp_path / "wt"
    repo_manager.cleanup_worktree.return_value = None
    slack = SlackNotifier(webhook_url="x", dry_run=True)

    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value=analyzer_result)

    github = AsyncMock(spec=GitHubClient)
    github.create_issue.return_value = IssueRef(number=42, url="https://github.com/x/y/issues/42")
    github.create_pull_request_with_patch.return_value = PullRequestRef(
        number=43, branch="ai-fix/issue-42", url="https://github.com/x/y/pull/43",
    )

    return Orchestrator(
        settings=settings, session_maker=session_maker,
        log_fetcher=log_fetcher, repo_manager=repo_manager,
        slack=slack, analyzer=analyzer, github=github,
    ), github


@pytest.mark.asyncio
async def test_code_bug_creates_issue_and_pr(settings, session_maker, tmp_path: Path) -> None:
    result = AnalysisResult(
        category="CODE_BUG", confidence=0.85, root_cause="NPE",
        patch=Patch(file_path="src/main/x.kt", old_content="a", new_content="b"),
        model="claude", cost_usd=0.1,
    )
    orch, github = _make_orchestrator(settings, session_maker, result, tmp_path=tmp_path)
    event = IncidentEvent(service="x", commit_sha="abc", error_class="NPE")
    await orch.handle(event)
    github.create_issue.assert_awaited_once()
    github.create_pull_request_with_patch.assert_awaited_once()


@pytest.mark.asyncio
async def test_data_anomaly_creates_issue_only_no_pr(settings, session_maker, tmp_path: Path) -> None:
    result = AnalysisResult(
        category="DATA_ANOMALY", confidence=0.82, root_cause="city empty",
        data_hypothesis="city='' for users 100..200",
        verification_sql=["SELECT 1"], verification_logql=["{x}"],
        model="claude", cost_usd=0.1,
    )
    orch, github = _make_orchestrator(settings, session_maker, result, tmp_path=tmp_path)
    event = IncidentEvent(service="x", commit_sha="abc", error_class="NPE")
    await orch.handle(event)
    github.create_issue.assert_awaited_once()
    github.create_pull_request_with_patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_benign_first_time_creates_pr_and_proposal_issue(settings, session_maker, tmp_path: Path) -> None:
    result = AnalysisResult(
        category="BENIGN_ERROR", confidence=0.88, root_cause="client disconnect",
        patch=Patch(file_path="src/main/h.kt", old_content="", new_content="x"),
        alert_rule_proposal="exception_class!=ClientAbortException",
        model="claude", cost_usd=0.1,
    )
    orch, github = _make_orchestrator(settings, session_maker, result, tmp_path=tmp_path)
    event = IncidentEvent(service="x", commit_sha="abc", error_class="ClientAbortException")
    await orch.handle(event)
    # 2 issues (main + alert proposal) + 1 PR
    assert github.create_issue.await_count == 2
    github.create_pull_request_with_patch.assert_awaited_once()


@pytest.mark.asyncio
async def test_low_confidence_falls_to_insufficient_branch(settings, session_maker, tmp_path: Path) -> None:
    result = AnalysisResult(
        category="CODE_BUG", confidence=0.5, root_cause="not sure",
        patch=Patch(file_path="src/main/x.kt", old_content="a", new_content="b"),
        model="claude", cost_usd=0.05,
    )
    orch, github = _make_orchestrator(settings, session_maker, result, tmp_path=tmp_path)
    event = IncidentEvent(service="x", commit_sha="abc", error_class="x")
    await orch.handle(event)
    # confidence < 0.7라 PR 없음 (Issue만)
    github.create_issue.assert_awaited_once()
    github.create_pull_request_with_patch.assert_not_awaited()
```

- [ ] **Step 3: 테스트 실행**

Run:
```bash
cd ai-bot
uv run pytest tests/integration/test_orchestrator_with_github.py tests/integration/test_orchestrator.py -v
```

Expected: PASS (Plan 2의 test_orchestrator.py도 함께 통과해야 함). 만약 Plan 2의 test_orchestrator.py가 GitHubClient 인자 누락으로 깨졌다면 그 테스트도 mock github 추가해서 수정.

> **Plan 2 test 수정**: `ai-bot/tests/integration/test_orchestrator.py`의 Orchestrator 생성 3곳에 다음 인자 추가:
> ```python
> github=AsyncMock(spec=GitHubClient)
> ```
> 그리고 import 추가: `from ai_bot.services.github_client import GitHubClient`

- [ ] **Step 4: Plan 2 test 수정**

`ai-bot/tests/integration/test_orchestrator.py`를 수정:

```python
# 파일 상단 import에 추가
from unittest.mock import AsyncMock
from ai_bot.services.github_client import GitHubClient

# 각 Orchestrator(...) 호출에 github 인자 추가:
#   orch = Orchestrator(
#       ...
#       analyzer=FakeAnalyzer(),
#       github=AsyncMock(spec=GitHubClient),  # ← 추가
#   )
```

3곳 모두 동일하게 수정 후 다시 테스트:

```bash
cd ai-bot
uv run pytest tests/integration/ -v
```

Expected: 모든 통합 테스트 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/orchestrator.py \
        ai-bot/tests/integration/test_orchestrator_with_github.py \
        ai-bot/tests/integration/test_orchestrator.py
git commit -m "feat(orchestrator): category-based Issue/PR routing with GitHubClient"
```

---

## Task 15: main.py 업데이트 — ClaudeAnalyzer + GitHubClient 주입

**Files:**
- Modify: `ai-bot/src/ai_bot/main.py`

- [ ] **Step 1: main.py 수정**

`ai-bot/src/ai_bot/main.py`의 `create_app` 함수를 다음으로 교체:

```python
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
    github = GitHubClient(
        token=_load_github_token(),
        repo_full_name=s.github_repo,
        dry_run=s.dry_run,
    )

    from ai_bot.analyzer.claude import ClaudeAnalyzer
    analyzer = ClaudeAnalyzer()

    orchestrator = Orchestrator(
        settings=s,
        session_maker=session_maker,
        log_fetcher=log_fetcher,
        repo_manager=repo_manager,
        slack=slack,
        analyzer=analyzer,
        github=github,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await repo_manager.ensure_bare_clone()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure_bare_clone failed at startup: %s — will retry per request", exc)
        logger.info("ai-bot ready (dry_run=%s, model=%s)", s.dry_run, analyzer._model)
        yield
        await engine.dispose()

    app = FastAPI(title="ai-bot", lifespan=lifespan)

    async def on_incident(event: IncidentEvent) -> None:
        await orchestrator.handle(event)

    app.include_router(build_router(settings=s, on_incident=on_incident))

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "dry_run": s.dry_run, "model": analyzer._model}

    return app


def _load_github_token() -> str:
    import os
    return os.environ.get("GITHUB_TOKEN", "")


app = create_app()
```

상단 import에 추가:
```python
from ai_bot.services.github_client import GitHubClient
```

- [ ] **Step 2: 로컬 기동 검증 (DRY_RUN=true로)**

Run:
```bash
cd ai-bot
WEBHOOK_TOKEN=dev-token LOKI_URL=http://localhost:3100 \
GITHUB_TOKEN=ghp_dummy_for_dry_run \
GITHUB_REPO=kiekk/demo-buggy-service \
GITHUB_REPO_URL=https://github.com/kiekk/demo-buggy-service.git \
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/dummy \
DB_PATH=/tmp/ai-bot-dev.db DRY_RUN=true \
REPO_CACHE_DIR=/tmp/ai-bot-repos WORKTREE_DIR=/tmp/ai-bot-wt \
ANTHROPIC_API_KEY=sk-ant-dummy \
uv run uvicorn ai_bot.main:app --host 0.0.0.0 --port 8090 &
SERVER_PID=$!
sleep 5
curl -s http://localhost:8090/health
echo
kill $SERVER_PID 2>/dev/null
```

Expected: `/health` 응답 `{"status":"ok","dry_run":true,"model":"claude-sonnet-4-6"}`

> 이 단계에선 webhook 호출 안 함 (실제 LLM 호출되면 비용 발생).

- [ ] **Step 3: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add ai-bot/src/ai_bot/main.py
git commit -m "feat(main): wire ClaudeAnalyzer + GitHubClient into orchestrator"
```

---

## Task 16: Dockerfile 업데이트 — Claude Code CLI 설치

**Files:**
- Modify: `ai-bot/Dockerfile`

Claude Agent SDK Python은 `claude` CLI를 subprocess로 spawn한다. 컨테이너에도 설치 필요.

- [ ] **Step 1: Dockerfile 수정**

`ai-bot/Dockerfile`을 다음으로 교체 (Node.js + Claude Code CLI 설치 단계 추가):

```dockerfile
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

RUN mkdir -p /data /data/repos /data/worktrees
ENV DB_PATH=/data/ai-bot.db
ENV REPO_CACHE_DIR=/data/repos
ENV WORKTREE_DIR=/data/worktrees

EXPOSE 8090

CMD ["sh", "-c", "alembic upgrade head && uvicorn ai_bot.main:app --host 0.0.0.0 --port 8090"]
```

- [ ] **Step 2: Docker build 검증**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose --profile demo build ai-bot
```

Expected: `claude` 명령 설치 포함된 이미지 빌드 성공. 빌드 시간 5분 내외.

- [ ] **Step 3: 컨테이너 내부에서 claude --version 확인**

Run:
```bash
docker run --rm --entrypoint claude $(docker images -q | head -1) --version
```

Expected: claude CLI 버전 출력

> 또는: `docker compose --profile demo up -d ai-bot` 후 `docker compose exec ai-bot claude --version`

- [ ] **Step 4: Commit**

```bash
git add ai-bot/Dockerfile
git commit -m "chore(docker): install Claude Code CLI (Agent SDK dependency) in ai-bot image"
```

---

## Task 17: End-to-end Plan 3 검증

**Files:** (검증 + README 갱신)

- [ ] **Step 1: 풀세트 기동**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose --profile demo down -v
docker compose --profile demo up -d --build
sleep 90
docker compose ps
docker compose logs ai-bot | tail -30
```

Expected:
- 모든 컨테이너 Up
- ai-bot 로그에 `alembic upgrade head` 성공, `ensure_bare_clone` 성공 (또는 token 문제 시 fallback), `ai-bot ready` 메시지

- [ ] **Step 2: 시나리오 1 (NPE) 트리거**

Run:
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js
sleep 120  # alert 평가 + LLM 분석 (1~2분 소요)
docker compose logs ai-bot | tail -50
```

Expected (ai-bot 로그):
- webhook 수신
- 🚨 에러 감지 메시지
- 🔍 분석 시작
- Claude Agent 도구 호출 흐름 (read_file, grep, ...)
- ✅ PR 생성 메시지 + GitHub URL

- [ ] **Step 3: GitHub 확인**

브라우저로 https://github.com/kiekk/demo-buggy-service/issues 와 https://github.com/kiekk/demo-buggy-service/pulls 접속.

Expected:
- 새 Issue: `[AI] NullPointerException in demo-buggy-service` 본문 + AI 메타정보
- 새 Draft PR: `[AI Fix] #N - ...` 본문 + `Fixes #N` + `human-review-required` 라벨
- PR diff에 의도된 null 체크 추가 같은 변경

- [ ] **Step 4: Slack 확인**

`ai-bot-demo` 채널에서 다음 메시지 흐름:
- 🚨 에러 감지
- 🔍 분석 시작
- ✅ PR 생성됨 + URL

- [ ] **Step 5: SQLite DB 검증**

Run:
```bash
docker compose exec ai-bot sqlite3 /data/ai-bot.db "SELECT id, status, category, confidence, pr_number, root_cause FROM analysis_runs;"
docker compose exec ai-bot sqlite3 /data/ai-bot.db "SELECT model, cost_usd, tool_calls_count, latency_ms FROM llm_usage;"
```

Expected:
- analysis_runs에 status=COMPLETED, category=CODE_BUG, confidence>=0.7, pr_number 채워짐
- llm_usage에 비용/토큰/도구 호출 수 기록

- [ ] **Step 6: Dedup 검증 — 같은 시나리오 재실행**

Run:
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js
sleep 60
docker compose logs ai-bot | tail -30
```

Expected: ai-bot 로그에 "🔁 기존 인시던트 재발" 메시지. 새 PR/Issue 생성 안 됨.

- [ ] **Step 7: 시나리오 2, 3도 검증**

Run:
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-2-divzero.js
sleep 150
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-3-enum.js
sleep 150
```

Expected: GitHub에 시나리오 2 (ArithmeticException), 3 (enum LEGACY_TYPE) 각각의 Issue + PR 생성

- [ ] **Step 8: 정리**

Run:
```bash
docker compose --profile demo down
```

> 시연용 PR들은 GitHub에 남겨두고 머지하지 말 것. 머지하면 다음 데모 때 시나리오 1~3 재현 불가.

- [ ] **Step 9: README 업데이트**

`README.md`의 "AI Incident Bot 데모" 섹션을 Plan 3로 갱신:

```markdown
## AI Incident Bot 데모 (Plan 3)

이제 시나리오 1~3 (CODE_BUG) 트리거 시 GitHub에 Issue + Draft PR이 자동 생성됩니다.

### 실행

```bash
cp .env.example .env
# .env 편집: ANTHROPIC_API_KEY, GITHUB_TOKEN, SLACK_WEBHOOK_URL, WEBHOOK_TOKEN 채우기
git submodule update --init --recursive
docker compose --profile demo up -d --build
```

### 검증

1. 시나리오 트리거: `docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js`
2. 2~3분 후 Slack `#ai-bot-demo` 채널에서 단계별 메시지 확인
3. GitHub https://github.com/kiekk/demo-buggy-service/pulls 에서 Draft PR 확인

> ⚠️ Draft PR은 시연용. 머지하면 의도적 버그가 사라져 시나리오 재현 불가.

### 비용

- 1회 시연 (시나리오 1~3 각 1번): 약 $1
- 일일 cap: `DAILY_COST_CAP_USD=5` (기본). 초과 시 자동 거절
```

- [ ] **Step 10: Final commit**

```bash
git add README.md
git commit -m "docs: update README for Plan 3 (Claude Agent + GitHub integration)"
```

---

## Plan 3 Out of Scope

- 시나리오 4 (DATA_ANOMALY), 5 (INFRA_ISSUE), 6 (BENIGN_ERROR) demo-buggy-service 코드 — Plan 4
- ai-bot 자체 Grafana 대시보드 (run 성공률, 비용, 카테고리 분포) — Plan 4
- DEMO_GUIDE.md — Plan 4
- Bedrock/Vertex 멀티 프로바이더 추상화 — 향후
- 토큰 절감을 위한 Haiku 1차 분류 라우팅 — 향후

---

## Plan 3 완료 시 산출물

- 시나리오 1~3 트리거 시 end-to-end로 GitHub에 Draft PR 자동 생성
- 5개 카테고리 분기 로직 모두 구현 (Plan 4의 시나리오에서 실제 발화)
- 안전장치 12종 중 PR 자동 머지 금지, confidence threshold, dedup, dry-run, cost cap, BENIGN 24h 차단 모두 동작
- SQLite에 incident/run/usage 기록
- Slack에 카테고리별 차별화된 메시지
- 도구 7종 + Pydantic 검증 + allowlist 강제
