"""
app/oee/engine.py
─────────────────
Query layer — ambil data dari DB lalu panggil formulas.py.

Menerjemahkan model SQLAlchemy → dict sederhana untuk formulas.py.
Semua logika kalkulasi ada di formulas.py, bukan di sini.

Query: 5 total
  1. master_lines
  2. master_shifts
  3. merged_lines + details
  4. master_standard_throughputs
  5. machine_loss_inputs (+ l1 category)
  6. production_outputs  (+ output_type.is_good_product)
  7. active dates (union ML inputs + prod outputs)
"""

from datetime import date, datetime
from typing import Optional
from collections import defaultdict

from sqlalchemy import cast, Date as SADate
from sqlalchemy.orm import Session

from app.models.plant_schema import (
    MachineLossInput, MachineLossLvl1,
    MasterLine, MasterShift,
    MasterStandardThroughput,
    MergedLine, MergedLineDetail,
    ProductionOutput, MasterOutputType,
)
from app.oee.formulas import compute_oee_metrics, SCHEDULED_L1, NON_OPERATING_L1s

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _to_date(v) -> date:
    return v.date() if isinstance(v, datetime) else v


def compute_time_metrics(
    db:        Session,
    date_from: date,
    date_to:   date,
    group_by:  str = "daily",
    line_ids:  Optional[list[int]] = None,
) -> list[dict]:
    """
    Query DB dan compute semua OEE metrics menggunakan logika dari measurement.ipynb.
    """
    dt_from = datetime.combine(date_from, datetime.min.time())
    dt_to   = datetime.combine(date_to,   datetime.max.time())

    # ── 1. Lines ──────────────────────────────────────────────────────────────
    line_q = db.query(MasterLine).filter(MasterLine.is_active == True)
    if line_ids:
        line_q = line_q.filter(MasterLine.id.in_(line_ids))
    lines = line_q.order_by(MasterLine.id).all()
    if not lines:
        return []
    line_id_list = [l.id for l in lines]
    lines_data   = [{"id": l.id, "name": l.name} for l in lines]

    # ── 2. Shifts ─────────────────────────────────────────────────────────────
    shifts = db.query(MasterShift).filter(MasterShift.is_active == True).all()
    if not shifts:
        return []
    shifts_data = [{"id": s.id, "name": s.name,
                    "time_from": s.time_from, "time_to": s.time_to}
                   for s in shifts]

    # ── 3. Merged lines ───────────────────────────────────────────────────────
    merged_lines_raw = (
        db.query(MergedLine)
        .filter(MergedLine.is_active == True)
        .all()
    )
    merged_lines_data: list[dict] = []
    for ml in merged_lines_raw:
        member_ids = [d.line_id for d in ml.details if d.line_id in set(line_id_list)]
        if len(member_ids) >= 2:
            member_names = [l.name for l in lines if l.id in set(member_ids)]
            merged_name  = " & ".join(member_names)
            merged_lines_data.append({"name": merged_name, "member_ids": member_ids})

    # ── 4. Standard throughputs ───────────────────────────────────────────────
    stp_rows = (
        db.query(
            MasterStandardThroughput.line_id,
            MasterStandardThroughput.feed_code_id,
            MasterStandardThroughput.standard_throughput,
        )
        .filter(MasterStandardThroughput.line_id.in_(line_id_list))
        .all()
    )
    # Notebook: std_throughput = std_output / final_operating_time
    # Di model kita: standard_throughput sudah merupakan unit/jam
    # Mapping: std_output = standard_throughput, final_op_time = 1 (sudah per jam)
    std_tps = [{"line_id": r.line_id, "feed_code_id": r.feed_code_id,
                "std_output": float(r.standard_throughput), "final_op_time": 1.0}
               for r in stp_rows]

    # ── 5. Machine loss inputs ────────────────────────────────────────────────
    loss_rows = (
        db.query(
            MachineLossInput.line_id,
            MachineLossInput.date,
            MachineLossInput.duration_minutes,
            MachineLossLvl1.name.label("l1_name"),
        )
        .outerjoin(
            MachineLossLvl1,
            MachineLossInput.loss_l1_id == MachineLossLvl1.machine_losses_lvl_1_id,
        )
        .filter(
            MachineLossInput.is_active == True,
            MachineLossInput.line_id.in_(line_id_list),
            MachineLossInput.date.between(dt_from, dt_to),
        )
        .all()
    )

    loss_data = [
        {
            "line_id":       r.line_id,
            "date":          _to_date(r.date),
            "duration_min":  float(r.duration_minutes or 0),
            "l1_name":       r.l1_name or "",
            # Scheduled = L1 name exact match (dari notebook: where t2.name = 'Scheduled Downtime')
            "is_scheduled":  (r.l1_name or "").strip() == SCHEDULED_L1,
            # Operating loss = bukan Scheduled, bukan Performance Loss, bukan Defects
            "is_operating":  (r.l1_name or "").strip() not in NON_OPERATING_L1s,
        }
        for r in loss_rows
    ]
    # Filter: hanya gunakan operating losses untuk operating_time (sesuai notebook)
    loss_data_filtered = [r for r in loss_data if r["is_scheduled"] or r["is_operating"]]

    # ── 6. Production outputs ─────────────────────────────────────────────────
    prod_rows = (
        db.query(
            ProductionOutput.line_id,
            ProductionOutput.date,
            ProductionOutput.quantity,
            MasterOutputType.is_good_product,
        )
        .join(
            MasterOutputType,
            ProductionOutput.output_type == MasterOutputType.code,
        )
        .filter(
            ProductionOutput.is_active == True,
            ProductionOutput.line_id.in_(line_id_list),
            ProductionOutput.date.between(dt_from, dt_to),
        )
        .all()
    )
    prod_data = [
        {
            "line_id":        r.line_id,
            "date":           _to_date(r.date),
            "quantity":       float(r.quantity or 0),
            "is_good_product": bool(r.is_good_product),
        }
        for r in prod_rows
    ]

    # ── 7. Active dates per line (union ML + PO) ──────────────────────────────
    active_days: dict[int, set] = defaultdict(set)
    for r in loss_rows:
        active_days[r.line_id].add(_to_date(r.date))
    for r in prod_rows:
        active_days[r.line_id].add(_to_date(r.date))

    # ── Compute ───────────────────────────────────────────────────────────────
    return compute_oee_metrics(
        lines           = lines_data,
        shifts          = shifts_data,
        merged_lines    = merged_lines_data,
        std_throughputs = std_tps,
        loss_inputs     = loss_data_filtered,
        prod_outputs    = prod_data,
        active_days     = active_days,
        date_from       = date_from,
        date_to         = date_to,
        group_by        = group_by,
    )
