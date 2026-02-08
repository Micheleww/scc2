#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _as_int_series(s: pd.Series) -> pd.Series:
    # Keep NA as <NA> with pandas nullable Int64.
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def _parse_date_parts(*, y: pd.Series, m: pd.Series, d: pd.Series) -> pd.Series:
    yy = _as_int_series(y)
    mm = _as_int_series(m)
    dd = _as_int_series(d)
    ok = yy.notna() & mm.notna() & dd.notna()
    out = pd.Series(pd.NaT, index=yy.index, dtype="datetime64[ns]")
    if ok.any():
        out.loc[ok] = pd.to_datetime(
            {
                "year": yy.loc[ok].astype(int),
                "month": mm.loc[ok].astype(int),
                "day": dd.loc[ok].astype(int),
            },
            errors="coerce",
        )
    return out


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    cur = date(year, month, 1)
    return (nxt - cur).days


def _month_date_index(year: int, month: int) -> pd.DatetimeIndex:
    n = _days_in_month(year, month)
    return pd.date_range(datetime(year, month, 1), periods=n, freq="D")


def _read_emdat(emdat_xlsx: Path) -> pd.DataFrame:
    df = pd.read_excel(emdat_xlsx, sheet_name="EM-DAT Data", engine="openpyxl")

    # Minimal field set used by later analysis.
    keep = [
        "DisNo.",
        "Historic",
        "Disaster Group",
        "Disaster Subgroup",
        "Disaster Type",
        "Disaster Subtype",
        "ISO",
        "Country",
        "Subregion",
        "Region",
        "Start Year",
        "Start Month",
        "Start Day",
        "End Year",
        "End Month",
        "End Day",
        "Total Deaths",
        "Total Affected",
        "Total Damage, Adjusted ('000 US$)",
    ]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise RuntimeError(f"EM-DAT missing required columns: {missing}")

    out = df[keep].copy()
    out = out.rename(
        columns={
            "DisNo.": "disno",
            "Historic": "historic",
            "Disaster Group": "disaster_group",
            "Disaster Subgroup": "disaster_subgroup",
            "Disaster Type": "disaster_type",
            "Disaster Subtype": "disaster_subtype",
            "ISO": "iso",
            "Country": "country",
            "Subregion": "subregion",
            "Region": "region",
            "Start Year": "start_year",
            "Start Month": "start_month",
            "Start Day": "start_day",
            "End Year": "end_year",
            "End Month": "end_month",
            "End Day": "end_day",
            "Total Deaths": "total_deaths",
            "Total Affected": "total_affected",
            "Total Damage, Adjusted ('000 US$)": "total_damage_adj_000_usd",
        }
    )

    out["start_year"] = _as_int_series(out["start_year"])
    out["start_month"] = _as_int_series(out["start_month"])
    out["start_day"] = _as_int_series(out["start_day"])
    out["end_year"] = _as_int_series(out["end_year"])
    out["end_month"] = _as_int_series(out["end_month"])
    out["end_day"] = _as_int_series(out["end_day"])

    out["start_date"] = _parse_date_parts(y=out["start_year"], m=out["start_month"], d=out["start_day"])
    out["end_date"] = _parse_date_parts(y=out["end_year"], m=out["end_month"], d=out["end_day"])
    out["start_day_missing"] = out["start_day"].isna() & out["start_year"].notna() & out["start_month"].notna()

    for col in ("total_deaths", "total_affected", "total_damage_adj_000_usd"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["disno"] = out["disno"].astype(str)
    for col in ("historic", "disaster_group", "disaster_subgroup", "disaster_type", "disaster_subtype", "iso", "country", "region", "subregion"):
        out[col] = out[col].astype("string")

    return out


def _read_owid_world(owid_csv: Path) -> pd.DataFrame:
    usecols = [
        "date",
        "location",
        "new_cases",
        "new_deaths",
        "new_cases_per_million",
        "new_deaths_per_million",
    ]
    df = pd.read_csv(owid_csv, usecols=usecols)
    df = df[df["location"] == "World"].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")

    for c in usecols[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["new_cases_fill0"] = df["new_cases"].fillna(0.0)
    df["new_deaths_fill0"] = df["new_deaths"].fillna(0.0)
    df["new_cases_per_million_fill0"] = df["new_cases_per_million"].fillna(0.0)
    df["new_deaths_per_million_fill0"] = df["new_deaths_per_million"].fillna(0.0)

    df = df.rename(columns={"date": "day"})[
        [
            "day",
            "new_cases",
            "new_deaths",
            "new_cases_per_million",
            "new_deaths_per_million",
            "new_cases_fill0",
            "new_deaths_fill0",
            "new_cases_per_million_fill0",
            "new_deaths_per_million_fill0",
        ]
    ]
    return df


def _read_owid_world_from_countries(owid_csv: Path) -> tuple[pd.DataFrame, float]:
    """
    Build a daily "World" series by summing country rows (iso_code not starting with OWID_).

    Rationale:
    - OWID's explicit 'World' row can be weekly/irregular in some snapshots (values on some days, zeros on others).
    - Summing countries keeps us within the same OWID dataset but yields a true daily series.
    """
    usecols = ["date", "iso_code", "new_cases", "new_deaths", "population"]
    date_sums_cases: dict[pd.Timestamp, float] = {}
    date_sums_deaths: dict[pd.Timestamp, float] = {}
    pop_by_iso: dict[str, float] = {}

    for chunk in pd.read_csv(owid_csv, usecols=usecols, chunksize=500_000):
        chunk = chunk.dropna(subset=["date", "iso_code"])
        chunk["iso_code"] = chunk["iso_code"].astype("string")
        # Keep countries only (avoid aggregates like OWID_WRL, OWID_EUR, etc.)
        chunk = chunk[~chunk["iso_code"].str.startswith("OWID_", na=False)]
        if chunk.empty:
            continue

        chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce")
        chunk = chunk.dropna(subset=["date"])
        if chunk.empty:
            continue

        # Population map (first non-null per iso_code)
        pop = pd.to_numeric(chunk["population"], errors="coerce")
        iso = chunk["iso_code"].astype(str)
        for i, p in zip(iso.values.tolist(), pop.values.tolist()):
            if i and i not in pop_by_iso and p is not None and np.isfinite(p) and p > 0:
                pop_by_iso[i] = float(p)

        # Sum daily new_cases/new_deaths (treat missing as 0).
        chunk["new_cases"] = pd.to_numeric(chunk["new_cases"], errors="coerce").fillna(0.0)
        chunk["new_deaths"] = pd.to_numeric(chunk["new_deaths"], errors="coerce").fillna(0.0)
        g = chunk.groupby(chunk["date"].dt.floor("D"), dropna=True).agg(new_cases=("new_cases", "sum"), new_deaths=("new_deaths", "sum"))
        for idx, row in g.iterrows():
            ts = pd.to_datetime(idx)
            date_sums_cases[ts] = float(date_sums_cases.get(ts, 0.0) + float(row["new_cases"]))
            date_sums_deaths[ts] = float(date_sums_deaths.get(ts, 0.0) + float(row["new_deaths"]))

    if not date_sums_cases and not date_sums_deaths:
        raise RuntimeError("OWID: no country rows found for aggregation (unexpected).")

    world_pop = float(sum(pop_by_iso.values())) if pop_by_iso else float("nan")

    days = sorted(set(date_sums_cases.keys()) | set(date_sums_deaths.keys()))
    df = pd.DataFrame({"day": pd.to_datetime(days)})
    df["new_cases"] = df["day"].map(date_sums_cases).fillna(0.0).astype(float)
    df["new_deaths"] = df["day"].map(date_sums_deaths).fillna(0.0).astype(float)
    if np.isfinite(world_pop) and world_pop > 0:
        df["new_cases_per_million"] = df["new_cases"] / world_pop * 1e6
        df["new_deaths_per_million"] = df["new_deaths"] / world_pop * 1e6
    else:
        df["new_cases_per_million"] = np.nan
        df["new_deaths_per_million"] = np.nan

    df["new_cases_fill0"] = df["new_cases"].fillna(0.0)
    df["new_deaths_fill0"] = df["new_deaths"].fillna(0.0)
    df["new_cases_per_million_fill0"] = df["new_cases_per_million"].fillna(0.0)
    df["new_deaths_per_million_fill0"] = df["new_deaths_per_million"].fillna(0.0)

    return df.sort_values("day").reset_index(drop=True), world_pop


def _calendar_features(days: pd.DatetimeIndex) -> pd.DataFrame:
    s = pd.Series(days, name="day")
    df = pd.DataFrame({"day": s})
    df["year"] = df["day"].dt.year.astype(int)
    df["month"] = df["day"].dt.month.astype(int)
    df["dom"] = df["day"].dt.day.astype(int)
    df["dow"] = df["day"].dt.dayofweek.astype(int)  # Monday=0
    df["is_friday"] = df["dow"] == 4
    df["is_friday_13"] = df["is_friday"] & (df["dom"] == 13)
    return df


@dataclass(frozen=True)
class EmdatVariant:
    name: str
    include_tech: bool
    missing_day: str  # "drop" | "uniform_month"


def _filter_group(df: pd.DataFrame, *, include_tech: bool) -> pd.DataFrame:
    if include_tech:
        return df[df["disaster_group"].isin(["Natural", "Technological"])].copy()
    return df[df["disaster_group"] == "Natural"].copy()


def _emdat_daily_counts(
    events: pd.DataFrame,
    *,
    include_tech: bool,
    missing_day: str,
) -> pd.DataFrame:
    if missing_day not in ("drop", "uniform_month"):
        raise ValueError("missing_day must be 'drop' or 'uniform_month'")

    df = _filter_group(events, include_tech=include_tech)

    # Always include exact-dated events.
    exact = df.dropna(subset=["start_date"]).copy()
    exact_daily = (
        exact.groupby(exact["start_date"].dt.floor("D"), dropna=True)
        .agg(
            emdat_event_count=("disno", "nunique"),
            emdat_total_deaths=("total_deaths", "sum"),
            emdat_total_affected=("total_affected", "sum"),
            emdat_total_damage_adj_000_usd=("total_damage_adj_000_usd", "sum"),
        )
        .reset_index()
        .rename(columns={"start_date": "day"})
    )

    if missing_day == "drop":
        return exact_daily

    # Distribute events with missing start day uniformly within their month.
    miss = df[df["start_date"].isna() & df["start_year"].notna() & df["start_month"].notna()].copy()
    if miss.empty:
        return exact_daily

    miss["start_year_i"] = miss["start_year"].astype(int)
    miss["start_month_i"] = miss["start_month"].astype(int)

    monthly = (
        miss.groupby(["start_year_i", "start_month_i"], dropna=False)
        .agg(
            emdat_event_count=("disno", "nunique"),
            emdat_total_deaths=("total_deaths", "sum"),
            emdat_total_affected=("total_affected", "sum"),
            emdat_total_damage_adj_000_usd=("total_damage_adj_000_usd", "sum"),
        )
        .reset_index()
    )

    pieces: list[pd.DataFrame] = [exact_daily]
    for r in monthly.itertuples(index=False):
        y = int(r.start_year_i)
        m = int(r.start_month_i)
        idx = _month_date_index(y, m)
        n = float(len(idx))
        if n <= 0:
            continue
        part = pd.DataFrame(
            {
                "day": idx,
                "emdat_event_count": float(r.emdat_event_count) / n,
                "emdat_total_deaths": (float(r.emdat_total_deaths) if pd.notna(r.emdat_total_deaths) else 0.0) / n,
                "emdat_total_affected": (float(r.emdat_total_affected) if pd.notna(r.emdat_total_affected) else 0.0) / n,
                "emdat_total_damage_adj_000_usd": (float(r.emdat_total_damage_adj_000_usd) if pd.notna(r.emdat_total_damage_adj_000_usd) else 0.0)
                / n,
            }
        )
        pieces.append(part)

    out = pd.concat(pieces, ignore_index=True)
    out = (
        out.groupby("day", as_index=False)
        .agg(
            emdat_event_count=("emdat_event_count", "sum"),
            emdat_total_deaths=("emdat_total_deaths", "sum"),
            emdat_total_affected=("emdat_total_affected", "sum"),
            emdat_total_damage_adj_000_usd=("emdat_total_damage_adj_000_usd", "sum"),
        )
        .sort_values("day")
    )
    return out


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    _ensure_dir(path.parent)
    df.to_parquet(path, index=False)


def _write_json(obj: object, path: Path) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _maybe_path(p: str) -> Optional[Path]:
    x = (p or "").strip()
    return Path(x) if x else None


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="IMMC Friday-13th ingest: EM-DAT + OWID (World) -> daily panels.")
    ap.add_argument("--emdat-xlsx", required=True, help="Path to EM-DAT public XLSX export (incl historical).")
    ap.add_argument("--owid-csv", required=True, help="Path to OWID owid-covid-data.csv.")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/ingest", help="Output directory (repo-relative by default).")
    args = ap.parse_args(list(argv) if argv is not None else None)

    repo_root = _repo_root()
    emdat_xlsx = Path(args.emdat_xlsx).expanduser()
    owid_csv = Path(args.owid_csv).expanduser()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (repo_root / out_dir).resolve()

    if not emdat_xlsx.exists():
        raise SystemExit(f"EM-DAT xlsx not found: {emdat_xlsx}")
    if not owid_csv.exists():
        raise SystemExit(f"OWID csv not found: {owid_csv}")

    _ensure_dir(out_dir)

    emdat_events = _read_emdat(emdat_xlsx)
    # Keep OWID 'World' row for reference, but use country-summed daily World for analysis panels.
    owid_world_row = _read_owid_world(owid_csv)
    owid_world, world_pop = _read_owid_world_from_countries(owid_csv)

    _write_parquet(emdat_events, out_dir / "emdat_events.parquet")
    _write_parquet(owid_world, out_dir / "owid_world_daily.parquet")
    _write_parquet(owid_world_row, out_dir / "owid_world_row_daily.parquet")

    variants = [
        EmdatVariant("natural__drop", include_tech=False, missing_day="drop"),
        EmdatVariant("natural__uniform_month", include_tech=False, missing_day="uniform_month"),
        EmdatVariant("nat_tech__drop", include_tech=True, missing_day="drop"),
        EmdatVariant("nat_tech__uniform_month", include_tech=True, missing_day="uniform_month"),
    ]

    daily_by_variant: dict[str, pd.DataFrame] = {}
    min_days: list[pd.Timestamp] = []
    max_days: list[pd.Timestamp] = []
    for v in variants:
        daily = _emdat_daily_counts(emdat_events, include_tech=v.include_tech, missing_day=v.missing_day)
        daily_by_variant[v.name] = daily
        if not daily.empty:
            min_days.append(pd.to_datetime(daily["day"].min()))
            max_days.append(pd.to_datetime(daily["day"].max()))

        _write_parquet(daily, out_dir / f"emdat_daily__{v.name}.parquet")
        _write_parquet(daily[daily["day"] >= "2000-01-01"].reset_index(drop=True), out_dir / f"emdat_daily__{v.name}__post2000.parquet")

    if not owid_world.empty:
        min_days.append(pd.to_datetime(owid_world["day"].min()))
        max_days.append(pd.to_datetime(owid_world["day"].max()))

    if not min_days or not max_days:
        raise SystemExit("No usable dates found in either EM-DAT or OWID inputs.")

    day0 = min(min_days)
    day1 = max(max_days)
    cal_days = pd.date_range(day0.floor("D"), day1.floor("D"), freq="D")
    calendar = _calendar_features(cal_days)
    _write_parquet(calendar, out_dir / "calendar_daily.parquet")

    # Panels: calendar + OWID + EM-DAT (variant).
    owid_idx = owid_world.copy()
    for v in variants:
        em = daily_by_variant[v.name]
        panel = calendar.merge(em, on="day", how="left").merge(owid_idx, on="day", how="left")
        for c in ("emdat_event_count", "emdat_total_deaths", "emdat_total_affected", "emdat_total_damage_adj_000_usd"):
            if c in panel.columns:
                panel[c] = panel[c].fillna(0.0)
        _write_parquet(panel, out_dir / f"panel__{v.name}.parquet")
        _write_parquet(panel[panel["day"] >= "2000-01-01"].reset_index(drop=True), out_dir / f"panel__{v.name}__post2000.parquet")

    def _count_nonnull(x: pd.Series) -> int:
        return int(x.notna().sum())

    summary = {
        "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            "emdat_xlsx": str(emdat_xlsx),
            "owid_csv": str(owid_csv),
        },
        "emdat": {
            "rows": int(len(emdat_events)),
            "unique_disno": int(emdat_events["disno"].nunique()),
            "start_date_nonnull": _count_nonnull(emdat_events["start_date"]),
            "start_day_missing_but_has_year_month": int(emdat_events["start_day_missing"].sum()),
            "min_start_year": int(emdat_events["start_year"].min()) if emdat_events["start_year"].notna().any() else None,
            "max_start_year": int(emdat_events["start_year"].max()) if emdat_events["start_year"].notna().any() else None,
            "disaster_group_counts": emdat_events["disaster_group"].value_counts(dropna=False).head(20).to_dict(),
        },
        "owid_world": {
            "method": "from_countries_sum_daily",
            "world_population_sum": world_pop,
            "rows": int(len(owid_world)),
            "min_day": str(owid_world["day"].min().date()) if not owid_world.empty else None,
            "max_day": str(owid_world["day"].max().date()) if not owid_world.empty else None,
            "new_deaths_nonnull": _count_nonnull(owid_world["new_deaths"]),
            "nonzero_new_deaths_days": int((owid_world["new_deaths"] > 0).sum()),
        },
        "owid_world_row_reference": {
            "rows": int(len(owid_world_row)),
            "min_day": str(owid_world_row["day"].min().date()) if not owid_world_row.empty else None,
            "max_day": str(owid_world_row["day"].max().date()) if not owid_world_row.empty else None,
            "nonzero_new_deaths_days": int((owid_world_row["new_deaths"] > 0).sum()),
        },
        "calendar": {"min_day": str(day0.date()), "max_day": str(day1.date()), "days": int(len(cal_days))},
        "variants": {v.name: {"rows_daily": int(len(daily_by_variant[v.name]))} for v in variants},
    }
    _write_json(summary, out_dir / "summary.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
