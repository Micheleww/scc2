"""Shared utilities for SCC tools."""
import json
import pathlib
from typing import Any


def norm_rel(p: str) -> str:
    """Normalize path to use forward slashes and remove leading ./"""
    return p.replace("\\", "/").lstrip("./")


def load_json(path: pathlib.Path) -> Any:
    """Load JSON file with UTF-8 encoding."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: pathlib.Path, data: Any) -> None:
    """Save data to JSON file with UTF-8 encoding."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_repo_root() -> pathlib.Path:
    """Get repository root path."""
    return pathlib.Path(__file__).resolve().parents[3]
