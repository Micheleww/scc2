from __future__ import annotations

import sys
from pathlib import Path


def _has_any(glob: str, root: Path) -> bool:
    return any(root.glob(glob))


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    wheelhouse = repo_root / "_wheelhouse"
    if not wheelhouse.exists():
        print(f"[wheelhouse] missing: {wheelhouse}")
        return 2

    # Minimal set that commonly breaks offline linux installs when wheelhouse is built on Windows.
    required = {
        "websockets": "websockets-*.whl",
        "uvloop": "uvloop-*.whl",
        "psutil": "psutil-*.whl",
        # Unified Server integrations
        "PyJWT": "PyJWT-*.whl",
        "Flask": "Flask-*.whl",
    }

    missing: list[str] = []
    for name, pattern in required.items():
        if not _has_any(pattern, wheelhouse):
            missing.append(name)

    if missing:
        print("[wheelhouse] missing linux wheels:", ", ".join(missing))
        print("[wheelhouse] hint: download manylinux wheels, e.g.")
        print(
            "python -m pip download --only-binary=:all: --platform manylinux_2_17_x86_64 "
            "--python-version 312 --implementation cp --abi cp312 -d _wheelhouse <pkg>"
        )
        return 3

    print("[wheelhouse] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
