from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


class FileLockError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, lock_path: Path):
        super().__init__(message)
        self.reason_code = str(reason_code or "file_lock_error")
        self.lock_path = Path(lock_path)


class FileLockTimeout(FileLockError):
    def __init__(self, message: str, *, lock_path: Path):
        super().__init__(message, reason_code="file_lock_timeout", lock_path=lock_path)


@dataclass(frozen=True)
class FileLockMeta:
    task_id: Optional[str] = None
    executor_id: Optional[str] = None
    pid: int = 0
    hostname: str = ""
    acquired_ts_utc: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "task_id": self.task_id,
            "executor_id": self.executor_id,
            "pid": int(self.pid or 0),
            "hostname": self.hostname,
            "acquired_ts_utc": self.acquired_ts_utc,
        }
        return {k: v for k, v in out.items() if v not in (None, "", 0)}


def default_workspace_lock_path(repo_root: Path) -> Path:
    """
    Coarse-grained lock used to serialize workspace writes in SCC workers.
    """
    repo_root = Path(repo_root).resolve()
    return (repo_root / "artifacts" / "scc_locks" / "workspace_write.lock").resolve()


class FileLock:
    """
    Minimal cross-process file lock.

    - Uses `portalocker` if available.
    - Falls back to stdlib-only locking:
      - Windows: msvcrt.locking (advisory)
      - POSIX: fcntl.flock (advisory)
    """

    def __init__(
        self,
        lock_path: Path,
        *,
        timeout_s: float = 300.0,
        poll_interval_s: float = 0.2,
        meta: Optional[FileLockMeta] = None,
    ):
        self.lock_path = Path(lock_path).resolve()
        self.timeout_s = float(timeout_s)
        self.poll_interval_s = float(poll_interval_s)
        self.meta = meta

        self._fh = None
        self._acquired = False

    @property
    def acquired(self) -> bool:
        return bool(self._acquired)

    def _read_owner_best_effort(self) -> Dict[str, Any]:
        try:
            if not self.lock_path.exists():
                return {}
            raw = self.lock_path.read_text(encoding="utf-8", errors="replace").strip()
            if not raw:
                return {}
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_owner_best_effort(self) -> None:
        try:
            if not self._fh:
                return
            meta = self.meta
            if meta is None:
                meta = FileLockMeta(
                    pid=os.getpid(),
                    hostname=socket.gethostname(),
                )
            payload = meta.to_dict()
            self._fh.seek(0)
            self._fh.truncate()
            self._fh.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            self._fh.flush()
            try:
                os.fsync(self._fh.fileno())
            except Exception:
                pass
        except Exception:
            return

    def _try_acquire_portalocker(self) -> bool:
        try:
            import portalocker  # type: ignore
        except Exception:
            return False

        lock = portalocker.Lock(
            str(self.lock_path),
            timeout=0,
            flags=portalocker.LOCK_EX,
        )
        try:
            self._fh = lock.acquire(timeout=0)
            self._acquired = True
            self._write_owner_best_effort()
            return True
        except portalocker.exceptions.LockException:  # type: ignore[attr-defined]
            return False

    def _try_acquire_fallback(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        fh = open(self.lock_path, "a+b")
        self._fh = fh

        try:
            fh.seek(0, os.SEEK_END)
            if fh.tell() < 1:
                fh.write(b"\0")
                fh.flush()
        except Exception:
            pass

        if os.name == "nt":
            import msvcrt

            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                self._acquired = True
                self._write_owner_best_effort()
                return True
            except OSError:
                try:
                    fh.close()
                except Exception:
                    pass
                self._fh = None
                return False
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._acquired = True
                self._write_owner_best_effort()
                return True
            except OSError:
                try:
                    fh.close()
                except Exception:
                    pass
                self._fh = None
                return False

    def acquire(self) -> None:
        start = time.time()
        owner_hint = self._read_owner_best_effort()

        while True:
            if self._acquired:
                return

            ok = self._try_acquire_portalocker()
            if not ok:
                ok = self._try_acquire_fallback()

            if ok:
                return

            waited = time.time() - start
            if self.timeout_s >= 0 and waited >= self.timeout_s:
                hint = f" owner={owner_hint!r}" if owner_hint else ""
                raise FileLockTimeout(
                    f"file_lock_timeout: could not acquire lock within {self.timeout_s:.1f}s for {self.lock_path}.{hint}",
                    lock_path=self.lock_path,
                )
            time.sleep(max(0.01, self.poll_interval_s))

    def release(self) -> None:
        if not self._fh:
            self._acquired = False
            return

        fh = self._fh
        self._fh = None
        try:
            if self._acquired:
                if os.name == "nt":
                    import msvcrt

                    try:
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                else:
                    import fcntl

                    try:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
        finally:
            self._acquired = False
            try:
                fh.close()
            except Exception:
                pass

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
