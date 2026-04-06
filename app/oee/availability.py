"""
app/oee/availability.py
───────────────────────
Service layer: query DB → kalkulasi → return hasil.
Logika bisnis ada di sini, bukan di endpoint.

Konsep:
  - scheduled_downtime: machine loss dengan L1 name mengandung kata
    "Scheduled" (case-insensitive). Dikurangkan dari total_time → loading_time.
  - operating_losses: semua machine loss SELAIN scheduled. Dikurangkan
    dari loading_time → operating_time.
  - total_time: dihitung dari shift (time_from → time_to) × jumlah hari
    yang memiliki machine loss record ATAU production output untuk line tsb.
"""

from datetime import date, datetime, timedelta
from typing import Optional
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.plant_schema import (
    MachineLossInput, MachineLossLvl1,
    MasterLine, MasterShift,
    ProductionOutput,
)
from app.oee.formulas import (
    calc_shift_hours,
    calc_loading_time,
    calc_operating_time,
    calc_availability_rate,
    calc_all_line_availability,
)


# ─── Keyword penanda "Scheduled Downtime" di L1 name ─────────────────────────
SCHEDULED_KEYWORDS = ["scheduled", "jadwal", "planned"]


def _is_scheduled(l1_name: str) -> bool:
    """True jika loss L1 termasuk kategori Scheduled Downtime."""
    name_lower = (l1_name or "").lower()
    return any(kw in name_lower for kw in SCHEDULED_KEYWORDS)


# ─── Query helpers ────────────────────────────────────────────────────────────

def _get_active_lines(db: Session, line_ids: Optional[list[int]] = None) -> list[MasterLine]:
    q = db.query(MasterLine).filter(MasterLine.is_active == True)
    if line_ids:
        q = q.filter(MasterLine.id.in_(line_ids))
    return q.order_by(MasterLine.id).all()


def _get_active_shifts(db: Session) -> list[MasterShift]:
    return db.query(MasterShift).filter(MasterShift.is_active == True).all()


def _get_loss_inputs(
    db: Session,
    date_from: date,
    date_to: date,
    line_ids: Optional[list[int]] = None,
) -> list[MachineLossInput]:
    """Ambil semua machine loss input dalam range tanggal, eager-load L1."""
    q = (
        db.query(MachineLossInput)
        .join(MachineLossLvl1, MachineLossInput.loss_l1_id == MachineLossLvl1.machine_losses_lvl_1_id, isouter=True)
        .filter(
            MachineLossInput.is_active == True,
            MachineLossInput.date >= datetime.combine(date_from, datetime.min.time()),
            MachineLossInput.date <= datetime.combine(date_to, datetime.max.time()),
        )
    )
    if line_ids:
        q = q.filter(MachineLossInput.line_id.in_(line_ids))
    return q.all()


def _collect_active_dates_per_line(
    db: Session,
    date_from: date,
    date_to: date,
    line_ids: list[int],
) -> dict[int, set[date]]:
    """
    Kumpulkan set tanggal aktif per line berdasarkan union:
      - tanggal ada machine_loss_inputs
      - tanggal ada production_outputs
    Ini menentukan berapa hari total_time dihitung.
    """
    result: dict[int, set[date]] = defaultdict(set)

    dt_from = datetime.combine(date_from, datetime.min.time())
    dt_to   = datetime.combine(date_to,   datetime.max.time())

    # Dari machine loss inputs
    loss_rows = (
        db.query(MachineLossInput.line_id, MachineLossInput.date)
        .filter(
            MachineLossInput.is_active == True,
            MachineLossInput.line_id.in_(line_ids),
            MachineLossInput.date >= dt_from,
            MachineLossInput.date <= dt_to,
        )
        .all()
    )
    for line_id, dt in loss_rows:
        result[line_id].add(dt.date() if isinstance(dt, datetime) else dt)

    # Dari production outputs
    prod_rows = (
        db.query(ProductionOutput.line_id, ProductionOutput.date)
        .filter(
            ProductionOutput.is_active == True,
            ProductionOutput.line_id.in_(line_ids),
            ProductionOutput.date >= dt_from,
            ProductionOutput.date <= dt_to,
        )
        .all()
    )
    for line_id, dt in prod_rows:
        result[line_id].add(dt.date() if isinstance(dt, datetime) else dt)

    return result


# ─── Main service function ────────────────────────────────────────────────────

def compute_availability_rate(
    db: Session,
    date_from: date,
    date_to: date,
    group_by: str = "daily",          # "daily" | "monthly"
    line_ids: Optional[list[int]] = None,
) -> list[dict]:
    """
    Hitung Availability Rate untuk semua line dalam range tanggal.

    Returns list of:
    {
      "date": "YYYY-MM-DD" | "YYYY-MM",
      "lines": {line_id: {"name": str, "rate": float|None, "loading_h": float, "operating_h": float}},
      "all_line": float | None
    }
    """
    lines  = _get_active_lines(db, line_ids)
    shifts = _get_active_shifts(db)
    if not lines or not shifts:
        return []

    line_map  = {l.id: l for l in lines}
    line_id_list = [l.id for l in lines]

    # Hitung total jam per shift
    shift_hours: dict[int, float] = {
        s.id: calc_shift_hours(s.time_from, s.time_to) for s in shifts
    }

    # Ambil semua loss inputs
    loss_inputs = _get_loss_inputs(db, date_from, date_to, line_id_list)

    # Dapatkan tanggal aktif per line
    active_dates_per_line = _collect_active_dates_per_line(
        db, date_from, date_to, line_id_list
    )

    # ── Group loss records ─────────────────────────────────────────────────
    # {bucket_key → {line_id → {sched_min, op_min, shift_ids_seen}}}
    # bucket_key = "YYYY-MM-DD" (daily) atau "YYYY-MM" (monthly)

    BucketData = dict  # {line_id: {"sched_min": float, "op_min": float, "shift_dates": set}}

    buckets: dict[str, BucketData] = defaultdict(lambda: defaultdict(
        lambda: {"sched_min": 0.0, "op_min": 0.0}
    ))

    for loss in loss_inputs:
        dt = loss.date if isinstance(loss.date, date) else loss.date.date()
        bucket = dt.strftime("%Y-%m") if group_by == "monthly" else dt.strftime("%Y-%m-%d")

        l1_name = loss.loss_l1.name if loss.loss_l1 else ""
        is_sched = _is_scheduled(l1_name)

        if is_sched:
            buckets[bucket][loss.line_id]["sched_min"] += loss.duration_minutes
        else:
            buckets[bucket][loss.line_id]["op_min"]    += loss.duration_minutes

    # ── Hitung total_time per bucket per line dari active_dates ───────────
    # Kumpulkan tanggal aktif ke bucket
    date_to_bucket: dict[date, str] = {}
    cur = date_from
    while cur <= date_to:
        bk = cur.strftime("%Y-%m") if group_by == "monthly" else cur.strftime("%Y-%m-%d")
        date_to_bucket[cur] = bk
        cur += timedelta(days=1)

    # total_time per bucket per line = jumlah hari aktif × total jam semua shift
    total_shift_hours = sum(shift_hours.values())

    total_time_per_bucket: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for line_id, active_dates in active_dates_per_line.items():
        for d in active_dates:
            if d < date_from or d > date_to:
                continue
            bk = date_to_bucket.get(d)
            if bk:
                total_time_per_bucket[bk][line_id] += total_shift_hours

    # ── Gabungkan semua bucket yang mungkin ada ───────────────────────────
    all_buckets: set[str] = set(buckets.keys()) | set(total_time_per_bucket.keys())

    results = []
    for bucket in sorted(all_buckets):
        line_results: dict[int, dict] = {}
        agg_op    = []
        agg_load  = []

        for line in lines:
            lid = line.id
            total_h = total_time_per_bucket[bucket].get(lid, 0.0)
            sched_h = round(buckets[bucket][lid]["sched_min"] / 60, 4)
            op_loss_h = round(buckets[bucket][lid]["op_min"] / 60, 4)

            loading_h   = calc_loading_time(total_h, sched_h)
            operating_h = calc_operating_time(loading_h, op_loss_h)
            rate        = calc_availability_rate(operating_h, loading_h)

            line_results[lid] = {
                "name":        line.name,
                "rate":        rate,
                "loading_h":   loading_h,
                "operating_h": operating_h,
                "total_h":     total_h,
                "sched_loss_h": sched_h,
                "op_loss_h":   op_loss_h,
            }

            if loading_h > 0:
                agg_op.append(operating_h)
                agg_load.append(loading_h)

        all_line = calc_all_line_availability(agg_op, agg_load)

        results.append({
            "date":     bucket,
            "lines":    line_results,
            "all_line": all_line,
        })

    return results
