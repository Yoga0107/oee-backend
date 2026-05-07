from datetime import date, datetime
from typing import Optional
from sqlalchemy import Date, cast
from sqlalchemy.orm import Session
from app.models.plant_schema import (
    MachineLossInput, MachineLossLvl1, MachineLossLvl2, MachineLossLvl3,
    MasterLine, MasterShift,
    MasterStandardThroughput, MasterFeedCode,
    MergedLine, ProductionOutput, MasterOutputType,
)
from app.oee.formulas import compute_oee_metrics, SCHEDULED_L1, NON_OPERATING_L1s


def _as_date(v) -> date:
    return v.date() if isinstance(v, datetime) else v


def compute_time_metrics(
    db: Session,
    date_from: date,
    date_to: date,
    group_by: str = "daily",
    line_ids: Optional[list[int]] = None,
) -> list[dict]:

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
    shifts = db.query(MasterShift).filter(MasterShift.is_active == True).order_by(MasterShift.id).all()
    if not shifts:
        return []
    shifts_data = [{"id": s.id, "name": s.name, "time_from": s.time_from, "time_to": s.time_to} for s in shifts]

    # ── 3. Merged lines ───────────────────────────────────────────────────────
    merged_lines_raw = db.query(MergedLine).filter(MergedLine.is_active == True).all()
    merged_lines_data: list[dict] = []
    line_id_set = set(line_id_list)
    for ml in merged_lines_raw:
        member_ids = [d.line_id for d in ml.details if d.line_id in line_id_set]
        if len(member_ids) >= 2:
            member_names = [l.name for l in lines if l.id in set(member_ids)]
            merged_lines_data.append({"name": " & ".join(member_names), "member_ids": member_ids})

    # ── 4. Standard throughputs ───────────────────────────────────────────────
    stp_rows = (
        db.query(
            MasterStandardThroughput.line_id,
            MasterStandardThroughput.feed_code_id,
            MasterStandardThroughput.standard_throughput,
            MasterFeedCode.code.label("feed_code"),
        )
        .join(MasterFeedCode, MasterStandardThroughput.feed_code_id == MasterFeedCode.id)
        .filter(MasterStandardThroughput.line_id.in_(line_id_list), MasterStandardThroughput.is_active == True)
        .all()
    )
    std_tps = [{"line_id": r.line_id, "feed_code_id": r.feed_code_id, "feed_code": r.feed_code,
                "std_output": float(r.standard_throughput), "final_op_time": 1.0} for r in stp_rows]

    # ── 5. Machine loss inputs — include shift_id ─────────────────────────────
    loss_date_col = cast(MachineLossInput.date, Date)
    loss_rows = (
        db.query(
            MachineLossInput.line_id,
            MachineLossInput.shift_id,
            loss_date_col.label("loss_date"),
            MachineLossInput.duration_minutes,
            MachineLossLvl1.name.label("l1_name"),
            MachineLossLvl2.name.label("l2_name"),
            MachineLossLvl3.name.label("l3_name"),
        )
        .outerjoin(MachineLossLvl1, MachineLossInput.loss_l1_id == MachineLossLvl1.machine_losses_lvl_1_id)
        .outerjoin(MachineLossLvl2, MachineLossInput.loss_l2_id == MachineLossLvl2.machine_losses_lvl_2_id)
        .outerjoin(MachineLossLvl3, MachineLossInput.loss_l3_id == MachineLossLvl3.machine_losses_lvl_3_id)
        .filter(
            MachineLossInput.is_active == True,
            MachineLossInput.line_id.in_(line_id_list),
            loss_date_col >= date_from,
            loss_date_col <= date_to,
        )
        .all()
    )

    loss_data = []
    for r in loss_rows:
        l1 = (r.l1_name or "").strip()
        l2 = (r.l2_name or "").strip()
        l3 = (r.l3_name or "").strip()
        loss_data.append({
            "line_id":      r.line_id,
            "shift_id":     r.shift_id,
            "date":         _as_date(r.loss_date),
            "duration_min": float(r.duration_minutes or 0),
            "l1_name":      l1, "l2_name": l2, "l3_name": l3,
            "is_scheduled": l1 == SCHEDULED_L1,
            "is_operating": l1 not in NON_OPERATING_L1s and l1 != "",
        })

    # ── 6. Production outputs ─────────────────────────────────────────────────
    prod_date_col = cast(ProductionOutput.date, Date)
    prod_rows = (
        db.query(
            ProductionOutput.line_id,
            prod_date_col.label("prod_date"),
            ProductionOutput.quantity,
            ProductionOutput.output_type,
            MasterOutputType.name.label("output_type_name"),
            MasterOutputType.is_good_product,
        )
        .join(MasterOutputType, ProductionOutput.output_type == MasterOutputType.code)
        .filter(
            ProductionOutput.is_active == True,
            ProductionOutput.line_id.in_(line_id_list),
            prod_date_col >= date_from,
            prod_date_col <= date_to,
        )
        .all()
    )
    prod_data = [
        {"line_id": r.line_id, "date": _as_date(r.prod_date),
         "quantity": float(r.quantity or 0), "output_type": r.output_type,
         "output_type_name": r.output_type_name or "", "is_good_product": bool(r.is_good_product)}
        for r in prod_rows
    ]

    return compute_oee_metrics(
        lines=lines_data, shifts=shifts_data, merged_lines=merged_lines_data,
        std_throughputs=std_tps, loss_inputs=loss_data, prod_outputs=prod_data,
        date_from=date_from, date_to=date_to, group_by=group_by,
    )
