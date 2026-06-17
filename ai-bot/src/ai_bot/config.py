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
