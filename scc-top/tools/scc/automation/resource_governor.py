#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resource governor: choose a safe max_outstanding based on CPU/memory pressure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from tools.scc.automation.system_metrics import SystemMetrics


def _f(env: str, default: float) -> float:
    try:
        return float(os.environ.get(env, "").strip() or default)
    except Exception:
        return float(default)


def _i(env: str, default: int) -> int:
    try:
        return int(os.environ.get(env, "").strip() or default)
    except Exception:
        return int(default)


@dataclass
class GovernorConfig:
    cpu_high: float = 0.75
    cpu_low: float = 0.55
    mem_high: float = 0.83
    mem_low: float = 0.75
    step: int = 1
    min_outstanding: int = 1
    max_outstanding: int = 3

    @staticmethod
    def from_env(*, default_max: int) -> "GovernorConfig":
        return GovernorConfig(
            cpu_high=_f("SCC_GOV_CPU_HIGH", 0.75),
            cpu_low=_f("SCC_GOV_CPU_LOW", 0.55),
            mem_high=_f("SCC_GOV_MEM_HIGH", 0.83),
            mem_low=_f("SCC_GOV_MEM_LOW", 0.75),
            step=max(1, _i("SCC_GOV_STEP", 1)),
            min_outstanding=max(1, _i("SCC_GOV_MIN_OUTSTANDING", 1)),
            max_outstanding=max(1, _i("SCC_GOV_MAX_OUTSTANDING", int(default_max))),
        )


def decide_max_outstanding(
    *,
    current: int,
    desired: int,
    limit: int,
    metrics: SystemMetrics,
    cfg: GovernorConfig,
) -> tuple[int, str]:
    """
    Returns (new_max, reason).
    """
    cur = max(cfg.min_outstanding, int(current or 1))
    desired = max(cfg.min_outstanding, int(desired or 1))
    limit = max(cfg.min_outstanding, int(limit or 1))
    ceiling = min(limit, cfg.max_outstanding, desired)

    cpu = metrics.cpu_percent
    mem = metrics.mem_percent
    # metrics are percent [0..100]; convert to [0..1]
    cpu_r = None if cpu is None else float(cpu) / 100.0
    mem_r = None if mem is None else float(mem) / 100.0

    too_hot = False
    cooling = False
    if cpu_r is not None and cpu_r >= cfg.cpu_high:
        too_hot = True
    if mem_r is not None and mem_r >= cfg.mem_high:
        too_hot = True
    if cpu_r is not None and cpu_r <= cfg.cpu_low and (mem_r is None or mem_r <= cfg.mem_low):
        cooling = True
    if mem_r is not None and mem_r <= cfg.mem_low and (cpu_r is None or cpu_r <= cfg.cpu_low):
        cooling = True

    if too_hot:
        nxt = max(cfg.min_outstanding, cur - cfg.step)
        return nxt, "pressure_high"
    if cooling and cur < ceiling:
        nxt = min(ceiling, cur + cfg.step)
        return nxt, "pressure_low"
    return min(cur, ceiling), "stable"

