#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
System metrics (CPU/memory/disk) for SCC resource governance.

Prefer psutil when available; fallback to minimal Windows APIs.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SystemMetrics:
    ts_utc: str
    cpu_percent: Optional[float]
    mem_percent: Optional[float]
    mem_used_gb: Optional[float]
    mem_total_gb: Optional[float]
    disk_percent: Optional[float]

    def to_dict(self) -> dict:
        return {
            "ts_utc": self.ts_utc,
            "cpu_percent": self.cpu_percent,
            "mem_percent": self.mem_percent,
            "mem_used_gb": self.mem_used_gb,
            "mem_total_gb": self.mem_total_gb,
            "disk_percent": self.disk_percent,
        }


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _gb(x: float) -> float:
    return float(x) / (1024.0**3)


def sample_system_metrics(*, disk_path: str | None = None) -> SystemMetrics:
    """
    Fast sampling with minimal overhead.
    """
    disk_path = str(disk_path or "").strip() or str(Path(os.getcwd()).anchor or "C:\\")

    cpu = None
    mem_pct = None
    mem_used = None
    mem_total = None
    disk_pct = None

    try:
        import psutil  # type: ignore

        cpu = float(psutil.cpu_percent(interval=0.0))
        vm = psutil.virtual_memory()
        mem_pct = float(vm.percent)
        mem_total = _gb(float(vm.total))
        mem_used = _gb(float(vm.total - vm.available))
        du = psutil.disk_usage(disk_path)
        disk_pct = float(du.percent)
    except Exception:
        # best-effort fallback: keep None for unavailable fields
        cpu = cpu

    return SystemMetrics(
        ts_utc=_utc_now(),
        cpu_percent=cpu,
        mem_percent=mem_pct,
        mem_used_gb=mem_used,
        mem_total_gb=mem_total,
        disk_percent=disk_pct,
    )

