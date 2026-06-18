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


def test_read_db_schema_no_migrations_returns_message(tmp_path: Path) -> None:
    ctx = ToolContext(worktree_path=tmp_path)
    result = read_db_schema(ctx, table=None)
    assert "no migration files" in result.lower()
