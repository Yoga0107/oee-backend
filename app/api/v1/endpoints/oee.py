"""
app/api/v1/endpoints/oee.py
───────────────────────────
Endpoint OEE View.

Pipeline (sesuai measurement.ipynb):
  total_time      = n_shifts × shift_hours × n_days          (deterministik)
  loading_time    = total_time  - Σ scheduled_downtime
  operating_time  = loading_time - Σ operating_losses
  availability    = operating_time / loading_time × 100
  performance     = actual_throughput / std_throughput × 100
  quality         = good_product / total_output × 100
  OEE             = A × P × Q / 10000

Endpoints:
  GET /oee/time-metrics      semua metrik sekaligus
  GET /oee/total-time        total time per line per bucket
  GET /oee/loading-time      loading time + sched breakdown
  GET /oee/operating-time    operating time + op breakdown
  GET /oee/availability-rate
  GET /oee/performance-rate
  GET /oee/quality-rate
  GET /oee/oee
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


# ─── Semua metrik sekaligus ───────────────────────────────────────────────────

@router.get("/time-metrics")
def get_time_metrics(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...),
    date_to:   date = Query(...),
    group_by:  str  = Query("daily"),
    line_ids:  Optional[str] = Query(None),
):
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {"data": data, **_meta(date_from, date_to, group_by)}


# ─── Total Time ───────────────────────────────────────────────────────────────

@router.get("/total-time")
def get_total_time(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...),
    date_to:   date = Query(...),
    group_by:  str  = Query("daily"),
    line_ids:  Optional[str] = Query(None),
):
    """
    Total Time = n_shifts × shift_hours × n_days_in_bucket.
    Deterministik — tidak bergantung pada ada/tidaknya data transaksi.
    all_line = Σ total_time semua line (non-merged-member).
    """
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {
        "data": [
            {
                "date": r["date"],
                "lines": {
                    str(lid): {"name": d["name"], "total_h": d["total_h"]}
                    for lid, d in r["lines"].items()
                },
                "all_line": r["all_line"]["total_h"],
            }
            for r in data
        ],
        **_meta(date_from, date_to, group_by),
    }


# ─── Loading Time ─────────────────────────────────────────────────────────────

@router.get("/loading-time")
def get_loading_time(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...),
    date_to:   date = Query(...),
    group_by:  str  = Query("daily"),
    line_ids:  Optional[str] = Query(None),
):
    """
    Loading Time = Total Time - Σ Scheduled Downtime.
    sched_breakdown: detail per (l1, l2, l3).
    all_line = Σ loading_time semua line (non-merged-member).
    """
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {
        "data": [
            {
                "date": r["date"],
                "lines": {
                    str(lid): {
                        "name":            d["name"],
                        "total_h":         d["total_h"],
                        "sched_loss_h":    d["sched_loss_h"],
                        "loading_h":       d["loading_h"],
                        "sched_breakdown": d["sched_breakdown"],
                    }
                    for lid, d in r["lines"].items()
                },
                "all_line": {
                    "total_h":         r["all_line"]["total_h"],
                    "sched_loss_h":    r["all_line"]["sched_loss_h"],
                    "loading_h":       r["all_line"]["loading_h"],
                    "sched_breakdown": r["all_line"]["sched_breakdown"],
                },
            }
            for r in data
        ],
        **_meta(date_from, date_to, group_by),
    }


# ─── Operating Time ───────────────────────────────────────────────────────────

@router.get("/operating-time")
def get_operating_time(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...),
    date_to:   date = Query(...),
    group_by:  str  = Query("daily"),
    line_ids:  Optional[str] = Query(None),
):
    """
    Operating Time = Loading Time - Σ Operating Losses (non-scheduled downtime).
    op_breakdown: detail per (l1, l2, l3).
    all_line = Σ operating_time semua line (non-merged-member).
    """
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {
        "data": [
            {
                "date": r["date"],
                "lines": {
                    str(lid): {
                        "name":         d["name"],
                        "loading_h":    d["loading_h"],
                        "op_loss_h":    d["op_loss_h"],
                        "operating_h":  d["operating_h"],
                        "op_breakdown": d["op_breakdown"],
                    }
                    for lid, d in r["lines"].items()
                },
                "all_line": {
                    "loading_h":    r["all_line"]["loading_h"],
                    "op_loss_h":    r["all_line"]["op_loss_h"],
                    "operating_h":  r["all_line"]["operating_h"],
                    "op_breakdown": r["all_line"]["op_breakdown"],
                },
            }
            for r in data
        ],
        **_meta(date_from, date_to, group_by),
    }


# ─── Availability ─────────────────────────────────────────────────────────────

@router.get("/availability-rate")
def get_availability_rate(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...),
    date_to:   date = Query(...),
    group_by:  str  = Query("daily"),
    line_ids:  Optional[str] = Query(None),
):
    """Availability = Operating Time / Loading Time × 100."""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {
        "data": [
            {
                "date": r["date"],
                "lines": {
                    str(lid): {
                        "name":            d["name"],
                        "total_h":         d["total_h"],
                        "sched_loss_h":    d["sched_loss_h"],
                        "op_loss_h":       d["op_loss_h"],
                        "loading_h":       d["loading_h"],
                        "operating_h":     d["operating_h"],
                        "availability":    d["availability"],
                        "sched_breakdown": d["sched_breakdown"],
                        "op_breakdown":    d["op_breakdown"],
                    }
                    for lid, d in r["lines"].items()
                },
                "all_line": {
                    "loading_h":    r["all_line"]["loading_h"],
                    "operating_h":  r["all_line"]["operating_h"],
                    "availability": r["all_line"]["availability"],
                },
            }
            for r in data
        ],
        **_meta(date_from, date_to, group_by),
    }


# ─── Performance ──────────────────────────────────────────────────────────────

@router.get("/performance-rate")
def get_performance_rate(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...),
    date_to:   date = Query(...),
    group_by:  str  = Query("daily"),
    line_ids:  Optional[str] = Query(None),
):
    """Performance = Actual Throughput / Std Throughput × 100."""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {
        "data": [
            {
                "date": r["date"],
                "lines": {
                    str(lid): {
                        "name":              d["name"],
                        "operating_h":       d["operating_h"],
                        "actual_output":     d["actual_output"],
                        "actual_throughput": d["actual_throughput"],
                        "std_throughput":    d["std_throughput"],
                        "performance":       d["performance"],
                    }
                    for lid, d in r["lines"].items()
                },
                "all_line": {
                    "actual_output": r["all_line"]["actual_output"],
                    "performance":   r["all_line"]["performance"],
                },
            }
            for r in data
        ],
        **_meta(date_from, date_to, group_by),
    }


# ─── Quality ──────────────────────────────────────────────────────────────────

@router.get("/quality-rate")
def get_quality_rate(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...),
    date_to:   date = Query(...),
    group_by:  str  = Query("daily"),
    line_ids:  Optional[str] = Query(None),
):
    """Quality = Good Product / Total Output × 100."""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {
        "data": [
            {
                "date": r["date"],
                "lines": {
                    str(lid): {
                        "name":         d["name"],
                        "actual_output": d["actual_output"],
                        "good_product": d["good_product"],
                        "quality":      d["quality"],
                    }
                    for lid, d in r["lines"].items()
                },
                "all_line": {
                    "actual_output": r["all_line"]["actual_output"],
                    "good_product":  r["all_line"]["good_product"],
                    "quality":       r["all_line"]["quality"],
                },
            }
            for r in data
        ],
        **_meta(date_from, date_to, group_by),
    }


# ─── OEE ──────────────────────────────────────────────────────────────────────

@router.get("/oee")
def get_oee(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...),
    date_to:   date = Query(...),
    group_by:  str  = Query("daily"),
    line_ids:  Optional[str] = Query(None),
):
    """OEE = Availability × Performance × Quality / 10000."""
    data = _run(plant, date_from, date_to, group_by, line_ids)
    return {
        "data": [
            {
                "date": r["date"],
                "lines": {
                    str(lid): {
                        "name":         d["name"],
                        "availability": d["availability"],
                        "performance":  d["performance"],
                        "quality":      d["quality"],
                        "oee":          d["oee"],
                    }
                    for lid, d in r["lines"].items()
                },
                "all_line": {
                    "availability": r["all_line"]["availability"],
                    "performance":  r["all_line"]["performance"],
                    "quality":      r["all_line"]["quality"],
                    "oee":          r["all_line"]["oee"],
                },
            }
            for r in data
        ],
        **_meta(date_from, date_to, group_by),
    }


# ─── DEBUG — hapus setelah verifikasi ─────────────────────────────────────────

@router.get("/debug-raw")
def debug_raw(
    current_user: CurrentUser, plant: CurrentPlant,
    date_from: date = Query(...),
    date_to:   date = Query(...),
):
    """
    Kembalikan raw data dari DB: shifts, lines, losses, productions.
    Untuk verifikasi apakah data sudah masuk dengan benar.
    """
    from datetime import datetime
    from app.models.plant_schema import (
        MasterShift, MasterLine, MachineLossInput,
        MachineLossLvl1, MachineLossLvl2, MachineLossLvl3,
        ProductionOutput, MasterOutputType,
    )
    dt_from = datetime.combine(date_from, datetime.min.time())
    dt_to   = datetime.combine(date_to,   datetime.max.time())

    db = next(get_plant_db(plant.schema_name))
    try:
        shifts = db.query(MasterShift).filter(MasterShift.is_active == True).all()
        lines  = db.query(MasterLine).filter(MasterLine.is_active == True).all()

        loss_rows = (
            db.query(
                MachineLossInput.id,
                MachineLossInput.line_id,
                MachineLossInput.date,
                MachineLossInput.duration_minutes,
                MachineLossLvl1.name.label("l1"),
                MachineLossLvl2.name.label("l2"),
                MachineLossLvl3.name.label("l3"),
            )
            .outerjoin(MachineLossLvl1, MachineLossInput.loss_l1_id == MachineLossLvl1.machine_losses_lvl_1_id)
            .outerjoin(MachineLossLvl2, MachineLossInput.loss_l2_id == MachineLossLvl2.machine_losses_lvl_2_id)
            .outerjoin(MachineLossLvl3, MachineLossInput.loss_l3_id == MachineLossLvl3.machine_losses_lvl_3_id)
            .filter(
                MachineLossInput.is_active == True,
                MachineLossInput.date.between(dt_from, dt_to),
            )
            .all()
        )

        prod_rows = (
            db.query(
                ProductionOutput.id,
                ProductionOutput.line_id,
                ProductionOutput.date,
                ProductionOutput.output_type,
                ProductionOutput.quantity,
                MasterOutputType.is_good_product,
            )
            .join(MasterOutputType, ProductionOutput.output_type == MasterOutputType.code)
            .filter(
                ProductionOutput.is_active == True,
                ProductionOutput.date.between(dt_from, dt_to),
            )
            .all()
        )

        return {
            "shifts": [
                {
                    "id": s.id, "name": s.name,
                    "time_from": str(s.time_from), "time_to": str(s.time_to),
                    "hours_actual": round(((s.time_to.hour*60+s.time_to.minute) - (s.time_from.hour*60+s.time_from.minute)) % 1440 / 60, 4)
                }
                for s in shifts
            ],
            "n_shifts_active": len(shifts),
            "total_time_per_line_per_day_formula": f"{len(shifts)} shifts × 8h = {len(shifts)*8}h",
            "lines": [{"id": l.id, "name": l.name} for l in lines],
            "total_shift_hours_per_day": round(
                sum(
                    ((s.time_to.hour*60+s.time_to.minute) - (s.time_from.hour*60+s.time_from.minute)) % 1440 / 60
                    for s in shifts
                ), 4
            ),
            "losses_count": len(loss_rows),
            "losses": [
                {
                    "id": r.id, "line_id": r.line_id,
                    "date": str(r.date), "duration_min": r.duration_minutes,
                    "l1": r.l1, "l2": r.l2, "l3": r.l3,
                }
                for r in loss_rows
            ],
            "productions_count": len(prod_rows),
            "productions": [
                {
                    "id": r.id, "line_id": r.line_id,
                    "date": str(r.date), "output_type": r.output_type,
                    "quantity": r.quantity, "is_good_product": r.is_good_product,
                }
                for r in prod_rows
            ],
        }
    finally:
        db.close()
