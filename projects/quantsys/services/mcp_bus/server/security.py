import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SecurityConfig:
    whitelist: list[str]
    blacklist: list[str]
    fail_closed: bool = True


class PathSecurity:
    def __init__(self, config: SecurityConfig, repo_root: str):
        self.config = config
        self.repo_root = Path(repo_root).resolve()

    def _normalize_path(self, path: str) -> Path:
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj.resolve()
        return (self.repo_root / path_obj).resolve()

    def _is_in_whitelist(self, path: Path) -> bool:
        rel_path = str(path.relative_to(self.repo_root)).replace("\\", "/")
        for allowed in self.config.whitelist:
            if rel_path.startswith(allowed.rstrip("/")):
                return True
        return False

    def _is_in_blacklist(self, path: Path) -> bool:
        rel_path = str(path.relative_to(self.repo_root)).replace("\\", "/")
        for blocked in self.config.blacklist:
            if rel_path.startswith(blocked.rstrip("/")):
                return True
        return False

    def check_access(self, path: str, mode: str = "read") -> tuple[bool, str]:
        try:
            normalized_path = self._normalize_path(path)

            # Python 3.8 compatible: use try/except instead of is_relative_to
            try:
                normalized_path.relative_to(self.repo_root)
            except ValueError:
                return False, f"Path outside repository root: {path}"

            if self._is_in_blacklist(normalized_path):
                return False, f"Path in blacklist: {path}"

            if not self._is_in_whitelist(normalized_path):
                return False, f"Path not in whitelist: {path}"

            return True, "Access granted"
        except Exception as e:
            return False, f"Path validation error: {str(e)}"

    def validate_path(self, path: str) -> tuple[bool, str, Path | None]:
        allowed, message = self.check_access(path)
        if allowed:
            return True, message, self._normalize_path(path)
        return False, message, None


def load_security_config(config_path: str, repo_root: str) -> SecurityConfig:
    with open(config_path) as f:
        config = json.load(f)

    security_config = config.get("security", {})
    return SecurityConfig(
        whitelist=security_config.get("whitelist", []),
        blacklist=security_config.get("blacklist", []),
        fail_closed=security_config.get("fail_closed", True),
    )
