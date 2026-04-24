"""
app/api/v1/endpoints/oee.py
───────────────────────────
Endpoint OEE View — implementasi dari measurement.ipynb.

Pipeline:
  total_time → loading_time → operating_time → availability
  actual/std throughput → performance
  good_product/total_output → quality
  availability × performance × quality / 10000 → OEE

Endpoint:
  GET /oee/time-metrics        → semua 5 metrik sekaligus
  GET /oee/loading-time        → alias
  GET /oee/operating-time      → alias
  GET /oee/availability-rate   → alias
  GET /oee/performance-rate    → alias
  GET /oee/quality-rate        → alias
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import CurrentUser, CurrentPlant
from app.db.database import get_plant_db
from app.oee.engine import compute_time_metrics

router = APIRouter(prefix="/oee", tags=["OEE"])


def _parse_line_ids(raw: Optional[str]) -> Optional[list[int]]:
    if not raw:
        return None
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "line_ids harus angka dipisah koma")


def _validate(date_from: date, date_to: date, group_by: str) -> None:
    if date_from > date_to:
        raise HTTPException(400, "date_from harus <= date_to")
    if (date_to - date_from).days > 366:
        raise HTTPException(400, "Range maksimal 366 hari")
    if group_by not in ("daily", "monthly"):
        raise HTTPException(400, "group_by harus 'daily' atau 'monthly'")


def _run(plant, date_from, date_to, group_by, line_ids_raw):
    _validate(date_from, date_to, group_by)
    db = next(get_plant_db(plant.schema_name))
    try:
        return compute_time_metrics(
            db=db, date_from=date_from, date_to=date_to,
            group_by=group_by, line_ids=_parse_line_ids(line_ids_raw),
        )
    finally:
        db.close()


def _meta(date_from, date_to, group_by):
    return {"date_from": str(date_from), "date_to": str(date_to), "group_by": group_by}


# ─── Endpoint utama — semua metrik sekaligus ─────────────────────────────────

@router.get("/time-metrics")
def get_time_metrics(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(..., description="YYYY-MM-DD"),
    date_to:   date = Query(..., description="YYYY-MM-DD"),
    group_by:  str  = Query("daily", description="'daily' | 'monthly'"),
    line_ids:  Optional[str] = Query(None, description="Comma-separated line IDs"),
):
    """
    Semua metrik OEE: loading_time, operating_time, availability,
    performance, quality, OEE — dari satu set query DB.
    """
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {"data": data, **_meta(date_from, date_to, group_by)}


# ─── Alias individual ────────────────────────────────────────────────────────

@router.get("/loading-time")
def get_loading_time(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...), date_to: date = Query(...),
    group_by: str = Query("daily"), line_ids: Optional[str] = Query(None),
):
    """Loading Time = Total Time − Σ Scheduled Downtime"""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {"data": [
        {"date": r["date"],
         "lines": {lid: {k: d[k] for k in ("name","total_h","sched_loss_h","loading_h")}
                   for lid, d in r["lines"].items()},
         "all_line": r["all_line"]["loading_h"]}
        for r in data
    ], **_meta(date_from, date_to, group_by)}


@router.get("/operating-time")
def get_operating_time(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...), date_to: date = Query(...),
    group_by: str = Query("daily"), line_ids: Optional[str] = Query(None),
):
    """Operating Time = Loading Time − Σ Operating Losses"""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {"data": [
        {"date": r["date"],
         "lines": {lid: {k: d[k] for k in ("name","loading_h","op_loss_h","operating_h")}
                   for lid, d in r["lines"].items()},
         "all_line": r["all_line"]["operating_h"]}
        for r in data
    ], **_meta(date_from, date_to, group_by)}


@router.get("/availability-rate")
def get_availability_rate(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...), date_to: date = Query(...),
    group_by: str = Query("daily"), line_ids: Optional[str] = Query(None),
):
    """Availability = Operating Time / Loading Time × 100%"""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {"data": [
        {"date": r["date"],
         "lines": {lid: {**{k: d[k] for k in ("name","loading_h","operating_h","total_h","sched_loss_h","op_loss_h")},
                         "rate": d["availability"]}
                   for lid, d in r["lines"].items()},
         "all_line": r["all_line"]["availability"]}
        for r in data
    ], **_meta(date_from, date_to, group_by)}


@router.get("/performance-rate")
def get_performance_rate(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...), date_to: date = Query(...),
    group_by: str = Query("daily"), line_ids: Optional[str] = Query(None),
):
    """Performance = Actual Throughput / Std Throughput × 100%"""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {"data": [
        {"date": r["date"],
         "lines": {lid: {k: d[k] for k in ("name","operating_h","actual_output",
                                             "actual_throughput","std_throughput","performance")}
                   for lid, d in r["lines"].items()},
         "all_line": {k: r["all_line"][k] for k in ("actual_output","performance")}}
        for r in data
    ], **_meta(date_from, date_to, group_by)}


@router.get("/quality-rate")
def get_quality_rate(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...), date_to: date = Query(...),
    group_by: str = Query("daily"), line_ids: Optional[str] = Query(None),
):
    """Quality = Good Product / Total Output × 100%"""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {"data": [
        {"date": r["date"],
         "lines": {lid: {k: d[k] for k in ("name","actual_output","good_product","quality")}
                   for lid, d in r["lines"].items()},
         "all_line": {k: r["all_line"][k] for k in ("actual_output","good_product","quality")}}
        for r in data
    ], **_meta(date_from, date_to, group_by)}


@router.get("/oee")
def get_oee(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...), date_to: date = Query(...),
    group_by: str = Query("daily"), line_ids: Optional[str] = Query(None),
):
    """OEE = Availability × Performance × Quality / 10000"""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {"data": [
        {"date": r["date"],
         "lines": {lid: {k: d[k] for k in ("name","availability","performance","quality","oee")}
                   for lid, d in r["lines"].items()},
         "all_line": {k: r["all_line"][k] for k in ("availability","performance","quality","oee")}}
        for r in data
    ], **_meta(date_from, date_to, group_by)}
