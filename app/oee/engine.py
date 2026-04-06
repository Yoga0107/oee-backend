from datetime import date, datetime
from typing import Optional
from collections import defaultdict

from sqlalchemy import cast, Date as SADate
from sqlalchemy.orm import Session

from app.models.plant_schema import (
    MachineLossInput, MachineLossLvl1,
    MasterLine, MasterShift,
    MasterStandardThroughput,
    ProductionOutput, MasterOutputType,
)
from app.oee.formulas import (
    calc_shift_hours, calc_loading_time, calc_operating_time,
    calc_availability, calc_all_line_rate,
    calc_ideal_output, calc_performance,
    calc_quality,
)

SCHEDULED_KEYWORDS = ("scheduled", "jadwal", "planned")


def _is_scheduled(name: str) -> bool:
    n = (name or "").lower()
    return any(kw in n for kw in SCHEDULED_KEYWORDS)


def _to_date(v) -> date:
    return v.date() if isinstance(v, datetime) else v


def _bk(d: date, group_by: str) -> str:
    return d.strftime("%Y-%m") if group_by == "monthly" else d.strftime("%Y-%m-%d")


# ─── Main engine ──────────────────────────────────────────────────────────────

def compute_time_metrics(
    db:        Session,
    date_from: date,
    date_to:   date,
    group_by:  str = "daily",
    line_ids:  Optional[list[int]] = None,
) -> list[dict]:

    # ── Query 1: Lines & Shifts ───────────────────────────────────────────
    line_q = db.query(MasterLine).filter(MasterLine.is_active == True)
    if line_ids:
        line_q = line_q.filter(MasterLine.id.in_(line_ids))
    lines = line_q.order_by(MasterLine.id).all()
    if not lines:
        return []

    shifts = db.query(MasterShift).filter(MasterShift.is_active == True).all()
    if not shifts:
        return []

    line_id_list  = [l.id for l in lines]
    line_map      = {l.id: l for l in lines}
    total_shift_h = sum(calc_shift_hours(s.time_from, s.time_to) for s in shifts)

    dt_from = datetime.combine(date_from, datetime.min.time())
    dt_to   = datetime.combine(date_to,   datetime.max.time())

    # ── Query 2: Standard Throughput per (line, feed_code) ───────────────
    tp_rows = (
        db.query(
            MasterStandardThroughput.line_id,
            MasterStandardThroughput.feed_code_id,
            MasterStandardThroughput.standard_throughput,
        )
        .filter(MasterStandardThroughput.line_id.in_(line_id_list))
        .all()
    )
    # throughput[line_id][feed_code_id] = std_throughput
    throughput: dict[int, dict[int, float]] = defaultdict(dict)
    for lid, fcid, stp in tp_rows:
        throughput[lid][fcid] = float(stp)

    # ── Query 3: Machine losses (join L1 name) ────────────────────────────
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

    # ── Query 4: Production outputs (join output_type for is_good_product) ─
    prod_rows = (
        db.query(
            ProductionOutput.line_id,
            ProductionOutput.date,
            ProductionOutput.feed_code_id,
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

    # ── Proses loss rows ──────────────────────────────────────────────────
    active_days: dict[int, set[date]]           = defaultdict(set)
    sched_min:   dict[str, dict[int, float]]    = defaultdict(lambda: defaultdict(float))
    op_min:      dict[str, dict[int, float]]    = defaultdict(lambda: defaultdict(float))

    for line_id, dt, dur_min, l1_name in loss_rows:
        d = _to_date(dt)
        active_days[line_id].add(d)
        bucket = _bk(d, group_by)
        if _is_scheduled(l1_name or ""):
            sched_min[bucket][line_id] += dur_min
        else:
            op_min[bucket][line_id]    += dur_min

    # ── Proses production rows ────────────────────────────────────────────
    # actual[bucket][line_id] = total actual output (semua tipe)
    # good[bucket][line_id]   = total good product saja
    # feed[bucket][line_id]   = set feed_code_id (untuk ambil std throughput)
    actual: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    good:   dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    # Weighted throughput: {bk: {line_id: Σ(qty × stp) / Σqty}}
    # Kita simpan numerator dan denominator terpisah
    stp_num: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    stp_den: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))

    for line_id, dt, feed_code_id, qty, is_good in prod_rows:
        d = _to_date(dt)
        active_days[line_id].add(d)
        bucket = _bk(d, group_by)

        actual[bucket][line_id] += qty
        if is_good:
            good[bucket][line_id] += qty

        # Throughput per unit produksi (weighted by qty)
        stp = throughput.get(line_id, {}).get(feed_code_id)
        if stp and qty > 0:
            stp_num[bucket][line_id] += qty * stp
            stp_den[bucket][line_id] += qty

    # ── total_time per (bucket, line_id) ─────────────────────────────────
    total_h_map: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for line_id, days in active_days.items():
        for d in days:
            if date_from <= d <= date_to:
                total_h_map[_bk(d, group_by)][line_id] += total_shift_h

    # ── Gabung semua bucket & kalkulasi ──────────────────────────────────
    all_buckets = sorted(
        set(total_h_map) | set(sched_min) | set(op_min) | set(actual)
    )

    results = []
    for bk in all_buckets:
        line_results: dict[int, dict] = {}

        # Aggregator all_line
        agg = {
            "total_h": 0.0, "sched_h": 0.0, "op_loss_h": 0.0,
            "load_list": [], "op_list": [],
            "actual": 0.0, "good": 0.0,
            "ideal_num": 0.0, "ideal_den": 0.0,
        }

        for lid in line_id_list:
            total_h   = total_h_map[bk].get(lid, 0.0)
            sched_h   = round(sched_min[bk].get(lid, 0.0) / 60, 4)
            op_loss_h = round(op_min[bk].get(lid, 0.0)    / 60, 4)

            loading_h   = calc_loading_time(total_h, sched_h)
            operating_h = calc_operating_time(loading_h, op_loss_h)
            avail       = calc_availability(operating_h, loading_h)

            # Throughput rata-rata tertimbang per kuantitas
            _stp_n = stp_num[bk].get(lid, 0.0)
            _stp_d = stp_den[bk].get(lid, 0.0)
            avg_stp = (_stp_n / _stp_d) if _stp_d > 0 else None

            act_qty  = actual[bk].get(lid, 0.0)
            good_qty = good[bk].get(lid, 0.0)

            ideal_h  = calc_ideal_output(operating_h, avg_stp) if avg_stp else 0.0
            perf     = calc_performance(act_qty, ideal_h)
            qual     = calc_quality(good_qty, act_qty)

            line_results[lid] = {
                "name"        : line_map[lid].name,
                "total_h"     : round(total_h, 4),
                "sched_loss_h": sched_h,
                "op_loss_h"   : op_loss_h,
                "loading_h"   : loading_h,
                "operating_h" : operating_h,
                "availability": avail,
                "actual_output": act_qty,
                "good_product" : good_qty,
                "ideal_output" : ideal_h,
                "performance"  : perf,
                "quality"      : qual,
            }

            # Akumulasi all_line
            agg["total_h"] += total_h
            if loading_h > 0:
                agg["load_list"].append(loading_h)
                agg["op_list"].append(operating_h)
            agg["actual"] += act_qty
            agg["good"]   += good_qty
            if avg_stp and operating_h > 0:
                agg["ideal_num"] += operating_h * avg_stp
                agg["ideal_den"] += operating_h

        # all_line calculations
        all_load = round(sum(agg["load_list"]), 4)
        all_op   = round(sum(agg["op_list"]),   4)
        all_ideal = round(agg["ideal_num"], 2) if agg["ideal_den"] > 0 else 0.0

        results.append({
            "date"  : bk,
            "lines" : line_results,
            "all_line": {
                "total_h"      : round(agg["total_h"], 4),
                "loading_h"    : all_load,
                "operating_h"  : all_op,
                "availability" : calc_all_line_rate(agg["op_list"], agg["load_list"]),
                "actual_output": agg["actual"],
                "good_product" : agg["good"],
                "ideal_output" : all_ideal,
                "performance"  : calc_performance(agg["actual"], all_ideal),
                "quality"      : calc_quality(agg["good"], agg["actual"]),
            },
        })

    return results
