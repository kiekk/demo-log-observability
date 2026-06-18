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
    """worktree 기준 상대 경로 → 절대 경로 + allowlist 검증.

    Raises:
        ToolError: allowlist 외 또는 worktree 밖
    """
    p = (worktree / relative_path).resolve()
    try:
        rel = p.relative_to(worktree.resolve())
    except ValueError:
        raise ToolError(f"path outside worktree: {relative_path}") from None
    rel_str = str(rel)
    # 파일/디렉토리 모두 허용: rel_str이 allowlist prefix로 시작하거나,
    # rel_str + "/" 가 allowlist prefix 중 하나와 일치하면 통과 (디렉토리 자체를 path_prefix로 전달하는 케이스)
    def _allowed(s: str) -> bool:
        if any(s.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
            return True
        # 디렉토리 자체가 허용 prefix인 경우 (trailing slash 없이 resolve됨)
        if any((s + "/").startswith(prefix) or prefix.startswith(s + "/") for prefix in ALLOWED_PATH_PREFIXES):
            return True
        return False

    if not _allowed(rel_str):
        raise ToolError(
            f"path not in allowlist: {rel_str}. Allowed prefixes: {ALLOWED_PATH_PREFIXES}"
        )
    return p
