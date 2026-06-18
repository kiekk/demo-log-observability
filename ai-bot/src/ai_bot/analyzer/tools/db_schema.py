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
