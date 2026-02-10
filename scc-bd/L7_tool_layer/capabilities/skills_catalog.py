from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    dir: str
    skill_md: str


@dataclass(frozen=True)
class SkillDetail(SkillMeta):
    body: str
    resources: Dict[str, List[str]]


def _parse_frontmatter(text: str) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None, None
    frontmatter, body = match.groups()
    meta: Dict[str, str] = {}
    for line in frontmatter.strip().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip("\"'")
    return meta, (body or "").strip()


def _list_dir_files(dir_path: Path) -> List[str]:
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    out: List[str] = []
    for p in sorted(dir_path.glob("*")):
        if p.is_file():
            out.append(p.name)
    return out


class SkillsCatalog:
    """
    Minimal Skills catalog (knowledge packages, not code).

    - Loads SKILL.md frontmatter for listing (Layer 1).
    - Loads full SKILL.md body + lists scripts/references/assets on demand (Layer 2/3).

    SCC does not execute any model here; this is purely catalog + IO.
    """

    def __init__(self, roots: Iterable[Path]):
        self.roots = [Path(r).resolve() for r in roots]
        self._index: Dict[str, SkillMeta] = {}
        self.reload()

    def reload(self) -> None:
        idx: Dict[str, SkillMeta] = {}
        for root in self.roots:
            if not root.exists() or not root.is_dir():
                continue
            for skill_dir in sorted(root.glob("*")):
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue
                try:
                    text = skill_md.read_text(encoding="utf-8")
                except Exception:
                    continue
                meta, _body = _parse_frontmatter(text)
                if not meta:
                    continue
                name = str(meta.get("name") or "").strip()
                desc = str(meta.get("description") or "").strip()
                if not name or not desc:
                    continue
                if name in idx:
                    # first win (stable); allow overriding by root order
                    continue
                idx[name] = SkillMeta(
                    name=name,
                    description=desc,
                    dir=str(skill_dir),
                    skill_md=str(skill_md),
                )
        self._index = idx

    def list(self) -> List[SkillMeta]:
        return [self._index[k] for k in sorted(self._index.keys())]

    def get(self, name: str) -> Optional[SkillDetail]:
        name = str(name or "").strip()
        if not name:
            return None
        meta = self._index.get(name)
        if not meta:
            return None
        skill_md = Path(meta.skill_md)
        try:
            text = skill_md.read_text(encoding="utf-8")
        except Exception:
            return None
        fm, body = _parse_frontmatter(text)
        if not fm or body is None:
            return None
        skill_dir = Path(meta.dir)
        resources = {
            "scripts": _list_dir_files(skill_dir / "scripts"),
            "references": _list_dir_files(skill_dir / "references"),
            "assets": _list_dir_files(skill_dir / "assets"),
        }
        return SkillDetail(**asdict(meta), body=body, resources=resources)


def default_skill_roots(repo_root: Path) -> List[Path]:
    """
    Resolve skill roots.

    - SCC_SKILL_ROOTS supports semicolon-separated paths (Windows-friendly).
    - Defaults to repo_root/skills if exists.
    """
    roots: List[Path] = []
    env = (os.environ.get("SCC_SKILL_ROOTS") or "").strip()
    if env:
        for part in env.split(";"):
            p = part.strip().strip("\"'")
            if p:
                roots.append(Path(p))
    default_repo_skills = (repo_root / "skills").resolve()
    if default_repo_skills.exists():
        roots.append(default_repo_skills)
    return roots


def build_default_catalog(*, repo_root: Path) -> SkillsCatalog:
    return SkillsCatalog(default_skill_roots(repo_root))

