"""
app/oee/loading_time.py
───────────────────────
Service layer untuk Loading Time.

Formula:
  loading_time (per shift per line) =
      total_time (jam shift) - sum(scheduled_downtime_losses)

  scheduled_downtime = machine loss dengan L1 name mengandung
      "scheduled" / "jadwal" / "planned" (case-insensitive)

  all_line = sum_i(loading_time_i)   ← bukan rata-rata, tapi total
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
from app.oee.formulas import calc_shift_hours, calc_loading_time

SCHEDULED_KEYWORDS = ["scheduled", "jadwal", "planned"]


def _is_scheduled(l1_name: str) -> bool:
    name_lower = (l1_name or "").lower()
    return any(kw in name_lower for kw in SCHEDULED_KEYWORDS)


# ✅ helper biar aman
def to_date(dt):
    return dt.date() if isinstance(dt, datetime) else dt


def compute_loading_time(
    db:        Session,
    date_from: date,
    date_to:   date,
    group_by:  str = "daily",          # "daily" | "monthly"
    line_ids:  Optional[list[int]] = None,
) -> list[dict]:
    """
    Hitung Loading Time per line per bucket tanggal.
    """

    # ── Master data ────────────────────────────────────────────────────────
    line_q = db.query(MasterLine).filter(MasterLine.is_active == True)
    if line_ids:
        line_q = line_q.filter(MasterLine.id.in_(line_ids))
    lines = line_q.order_by(MasterLine.id).all()

    shifts = db.query(MasterShift).filter(MasterShift.is_active == True).all()

    if not lines or not shifts:
        return []

    line_id_list  = [l.id for l in lines]
    total_shift_h = sum(calc_shift_hours(s.time_from, s.time_to) for s in shifts)

    # ── Range datetime (untuk query DB) ────────────────────────────────────
    dt_from = datetime.combine(date_from, datetime.min.time())
    dt_to   = datetime.combine(date_to,   datetime.max.time())

    # ── Ambil machine loss ─────────────────────────────────────────────────
    loss_rows = (
        db.query(MachineLossInput)
        .join(
            MachineLossLvl1,
            MachineLossInput.loss_l1_id == MachineLossLvl1.machine_losses_lvl_1_id,
            isouter=True,
        )
        .filter(
            MachineLossInput.is_active == True,
            MachineLossInput.line_id.in_(line_id_list),
            MachineLossInput.date >= dt_from,
            MachineLossInput.date <= dt_to,
        )
        .all()
    )

    # ── Scheduled losses per (bucket, line_id) ────────────────────────────
    sched_min: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))

    for row in loss_rows:
        l1_name = row.loss_l1.name if row.loss_l1 else ""
        if not _is_scheduled(l1_name):
            continue

        dt = to_date(row.date)  # ✅ FIX utama

        bk = dt.strftime("%Y-%m") if group_by == "monthly" else dt.strftime("%Y-%m-%d")
        sched_min[bk][row.line_id] += row.duration_minutes

    # ── Tanggal aktif per line ─────────────────────────────────────────────
    active: dict[int, set[date]] = defaultdict(set)

    # dari machine loss
    for row in loss_rows:
        dt = to_date(row.date)  # ✅ FIX utama
        active[row.line_id].add(dt)

    # dari production output
    prod_rows = (
        db.query(ProductionOutput.line_id, ProductionOutput.date)
        .filter(
            ProductionOutput.is_active == True,
            ProductionOutput.line_id.in_(line_id_list),
            ProductionOutput.date >= dt_from,
            ProductionOutput.date <= dt_to,
        )
        .all()
    )

    for line_id, dt in prod_rows:
        d = to_date(dt)  # ✅ FIX utama
        active[line_id].add(d)

    # ── total_time per (bucket, line_id) ──────────────────────────────────
    total_h_map: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))

    for line_id, dates in active.items():
        for d in dates:
            # sekarang aman (date vs date)
            if d < date_from or d > date_to:
                continue

            bk = d.strftime("%Y-%m") if group_by == "monthly" else d.strftime("%Y-%m-%d")
            total_h_map[bk][line_id] += total_shift_h

    # ── Gabungkan semua bucket ─────────────────────────────────────────────
    all_buckets = sorted(set(sched_min.keys()) | set(total_h_map.keys()))

    line_map = {l.id: l for l in lines}
    results  = []

    for bk in all_buckets:
        line_results: dict[int, dict] = {}
        all_line_total = 0.0

        for lid, line in line_map.items():
            total_h   = total_h_map[bk].get(lid, 0.0)
            sched_h   = round(sched_min[bk].get(lid, 0.0) / 60, 4)
            loading_h = calc_loading_time(total_h, sched_h)

            line_results[lid] = {
                "name"        : line.name,
                "total_h"     : total_h,
                "sched_loss_h": sched_h,
                "loading_h"   : loading_h,
            }

            all_line_total += loading_h

        results.append({
            "date"    : bk,
            "lines"   : line_results,
            "all_line": round(all_line_total, 4),
        })

    return results