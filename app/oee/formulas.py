"""
app/oee/formulas.py
───────────────────
Pipeline per (date, line, shift):
  total_time     = 8h (hardcode, sesuai notebook: total_days × 8)
  loading_time   = total_time - Σ scheduled_downtime pada (date, line, shift)
  operating_time = loading_time - Σ operating_losses pada (date, line, shift)
  ...
"""

from datetime import date, datetime, timedelta
from typing import Optional

SCHEDULED_L1   = "Scheduled Downtime"
PERFORMANCE_L1 = "Performance Loss"
DEFECT_L1      = "Defects & Rework Loss"
NON_OPERATING_L1s = {SCHEDULED_L1, PERFORMANCE_L1, DEFECT_L1}

HOURS_PER_SHIFT = 8.0


def _safe_rate(num: float, den: float) -> Optional[float]:
    if den <= 0:
        return None
    return round(num / den * 100, 2)


def _bucket(d, group_by: str) -> str:
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%Y-%m") if group_by == "monthly" else d.strftime("%Y-%m-%d")


def _all_buckets(date_from: date, date_to: date, group_by: str) -> list[str]:
    buckets, seen = [], set()
    d = date_from
    while d <= date_to:
        b = _bucket(d, group_by)
        if b not in seen:
            buckets.append(b)
            seen.add(b)
        d += timedelta(days=1)
    return buckets


def _days_in_bucket(bucket: str, group_by: str) -> int:
    if group_by == "monthly":
        y, m = int(bucket[:4]), int(bucket[5:7])
        next_m = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        return (next_m - date(y, m, 1)).days
    return 1


def compute_oee_metrics(
    *,
    lines: list[dict],
    shifts: list[dict],
    merged_lines: list[dict],
    std_throughputs: list[dict],
    loss_inputs: list[dict],
    prod_outputs: list[dict],
    date_from: date,
    date_to: date,
    group_by: str = "daily",
) -> list[dict]:
    """
    Returns list of bucket dicts. Each bucket:
    {
      date, n_shifts, hours_per_shift,
      lines: {
        line_id: {
          name, shifts: {
            shift_id: {
              shift_name, total_h, sched_loss_h, loading_h,
              op_loss_h, operating_h, sched_breakdown, op_breakdown
            }
          },
          total_h, sched_loss_h, loading_h, op_loss_h, operating_h,
          availability, performance, quality, oee,
          actual_output, good_product, std_throughput, actual_throughput,
          sched_breakdown, op_breakdown
        }
      },
      all_line: { ... aggregated ... }
    }
    """
    line_id_list   = [l["id"] for l in lines]
    line_id_map    = {l["id"]: l["name"] for l in lines}
    shift_id_map   = {s["id"]: s["name"] for s in shifts}
    shift_id_list  = [s["id"] for s in shifts]
    ml_map         = {m["name"]: m["member_ids"] for m in merged_lines}
    merged_members: set[int] = {lid for m in merged_lines for lid in m["member_ids"]}

    # ── Standard throughput per line ──────────────────────────────────────────
    stp_num: dict[int, float] = {}
    stp_den: dict[int, float] = {}
    for row in std_throughputs:
        lid = row["line_id"]
        stp_num[lid] = stp_num.get(lid, 0.0) + float(row["std_output"] or 0)
        stp_den[lid] = stp_den.get(lid, 0.0) + float(row["final_op_time"] or 0)
    std_tp: dict[int, float] = {
        lid: (stp_num[lid] / stp_den[lid]) if stp_den.get(lid, 0) > 0 else 0.0
        for lid in stp_num
    }

    # ── Aggregate losses per (bucket, line_id, shift_id) ─────────────────────
    # Key: (bucket, line_id, shift_id) → hours
    sched_h: dict[tuple, float] = {}
    op_h:    dict[tuple, float] = {}
    # Breakdown key: (bucket, line_id, shift_id) → {(l1,l2,l3): hours}
    sched_bd: dict[tuple, dict] = {}
    op_bd:    dict[tuple, dict] = {}

    for row in loss_inputs:
        b   = _bucket(row["date"], group_by)
        lid = row["line_id"]
        sid = row["shift_id"]
        dur = float(row["duration_min"] or 0) / 60
        k   = (b, lid, sid)
        lvl = (row["l1_name"], row["l2_name"], row["l3_name"])

        if row["is_scheduled"]:
            sched_h[k] = sched_h.get(k, 0.0) + dur
            sched_bd.setdefault(k, {})
            sched_bd[k][lvl] = sched_bd[k].get(lvl, 0.0) + dur
        elif row["is_operating"]:
            op_h[k] = op_h.get(k, 0.0) + dur
            op_bd.setdefault(k, {})
            op_bd[k][lvl] = op_bd[k].get(lvl, 0.0) + dur

    # ── Aggregate production per (bucket, line_id) ────────────────────────────
    total_out: dict[tuple, float] = {}
    good_out:  dict[tuple, float] = {}
    for row in prod_outputs:
        b   = _bucket(row["date"], group_by)
        lid = row["line_id"]
        k   = (b, lid)
        qty = float(row["quantity"] or 0)
        total_out[k] = total_out.get(k, 0.0) + qty
        if row["is_good_product"]:
            good_out[k] = good_out.get(k, 0.0) + qty

    # ── Iterate all buckets ───────────────────────────────────────────────────
    all_bk = _all_buckets(date_from, date_to, group_by)
    results = []

    for bucket in all_bk:
        n_days = _days_in_bucket(bucket, group_by)
        # total_time per (line, shift) per bucket = 8h × n_days
        tt = round(HOURS_PER_SHIFT * n_days, 6)

        line_results: dict = {}

        # ── Per individual line ────────────────────────────────────────────────
        for lid in line_id_list:
            shift_detail: dict = {}
            line_sched_h  = 0.0
            line_op_h     = 0.0
            line_sched_bd: dict = {}
            line_op_bd:    dict = {}

            for sid in shift_id_list:
                k = (bucket, lid, sid)
                sd  = sched_h.get(k, 0.0)
                nsd = op_h.get(k, 0.0)
                lt  = max(0.0, round(tt - sd,  6))
                ot  = max(0.0, round(lt - nsd, 6))

                # Breakdown per shift
                s_bd = [{"l1": lv[0], "l2": lv[1], "l3": lv[2], "hours": round(v, 4)}
                        for lv, v in sorted(sched_bd.get(k, {}).items())]
                o_bd = [{"l1": lv[0], "l2": lv[1], "l3": lv[2], "hours": round(v, 4)}
                        for lv, v in sorted(op_bd.get(k, {}).items())]

                shift_detail[sid] = {
                    "shift_name":   shift_id_map[sid],
                    "total_h":      round(tt,  4),
                    "sched_loss_h": round(sd,  4),
                    "loading_h":    round(lt,  4),
                    "op_loss_h":    round(nsd, 4),
                    "operating_h":  round(ot,  4),
                    "sched_breakdown": s_bd,
                    "op_breakdown":    o_bd,
                }

                line_sched_h += sd
                line_op_h    += nsd
                for lv, v in sched_bd.get(k, {}).items():
                    line_sched_bd[lv] = line_sched_bd.get(lv, 0.0) + v
                for lv, v in op_bd.get(k, {}).items():
                    line_op_bd[lv] = line_op_bd.get(lv, 0.0) + v

            # Totals per line (sum across shifts)
            line_tt = tt * len(shift_id_list)
            line_lt = max(0.0, round(line_tt - line_sched_h, 6))
            line_ot = max(0.0, round(line_lt - line_op_h,   6))

            prod_k = (bucket, lid)
            tout = total_out.get(prod_k, 0.0)
            gout = good_out.get(prod_k, 0.0)
            stp  = std_tp.get(lid, 0.0)

            avail   = _safe_rate(line_ot, line_lt)
            act_tp  = round(tout / line_ot, 4) if line_ot > 0 else 0.0
            perf    = _safe_rate(act_tp, stp) if stp > 0 and lid not in merged_members else None
            qual    = _safe_rate(gout, tout)  if tout > 0 and lid not in merged_members else None
            oee_val: Optional[float] = None
            if avail and perf and qual:
                oee_val = round(avail * perf * qual / 10_000, 2)

            line_results[lid] = {
                "name":             line_id_map[lid],
                "shifts":           shift_detail,
                "total_h":          round(line_tt, 4),
                "sched_loss_h":     round(line_sched_h, 4),
                "loading_h":        round(line_lt, 4),
                "op_loss_h":        round(line_op_h, 4),
                "operating_h":      round(line_ot, 4),
                "actual_output":    round(tout, 4),
                "good_product":     round(gout, 4),
                "std_throughput":   round(stp, 4),
                "actual_throughput":act_tp,
                "availability":     avail,
                "performance":      perf,
                "quality":          qual,
                "oee":              oee_val,
                "sched_breakdown":  [{"l1":lv[0],"l2":lv[1],"l3":lv[2],"hours":round(v,4)} for lv,v in sorted(line_sched_bd.items())],
                "op_breakdown":     [{"l1":lv[0],"l2":lv[1],"l3":lv[2],"hours":round(v,4)} for lv,v in sorted(line_op_bd.items())],
            }

        # ── Merged lines ───────────────────────────────────────────────────────
        for ml_name, member_ids in ml_map.items():
            ml_shifts: dict = {}
            for sid in shift_id_list:
                ml_sd  = sum(sched_h.get((bucket, lid, sid), 0.0) for lid in member_ids)
                ml_nsd = sum(op_h.get((bucket, lid, sid), 0.0)    for lid in member_ids)
                ml_tt  = tt * len(member_ids)
                ml_lt  = max(0.0, round(ml_tt - ml_sd, 6))
                ml_ot  = max(0.0, round(ml_lt - ml_nsd, 6))
                ml_shifts[sid] = {
                    "shift_name": shift_id_map[sid],
                    "total_h": round(ml_tt, 4), "sched_loss_h": round(ml_sd, 4),
                    "loading_h": round(ml_lt, 4), "op_loss_h": round(ml_nsd, 4), "operating_h": round(ml_ot, 4),
                    "sched_breakdown": [], "op_breakdown": [],
                }
            ml_tt_total = tt * len(member_ids) * len(shift_id_list)
            ml_sd_total = sum(line_results.get(lid, {}).get("sched_loss_h", 0) for lid in member_ids)
            ml_lt_total = max(0.0, round(ml_tt_total - ml_sd_total, 6))
            ml_nsd_total= sum(line_results.get(lid, {}).get("op_loss_h",    0) for lid in member_ids)
            ml_ot_total = max(0.0, round(ml_lt_total - ml_nsd_total, 6))
            ml_tout     = sum(line_results.get(lid, {}).get("actual_output", 0) for lid in member_ids)
            ml_gout     = sum(line_results.get(lid, {}).get("good_product",  0) for lid in member_ids)
            line_results[ml_name] = {
                "name": ml_name, "shifts": ml_shifts,
                "total_h": round(ml_tt_total, 4), "sched_loss_h": round(ml_sd_total, 4),
                "loading_h": round(ml_lt_total, 4), "op_loss_h": round(ml_nsd_total, 4),
                "operating_h": round(ml_ot_total, 4),
                "actual_output": round(ml_tout, 4), "good_product": round(ml_gout, 4),
                "std_throughput": 0, "actual_throughput": 0,
                "availability": _safe_rate(ml_ot_total, ml_lt_total),
                "performance": None, "quality": None, "oee": None,
                "sched_breakdown": [], "op_breakdown": [],
            }

        # ── all_line — non-merged-members only ────────────────────────────────
        valid = [v for lid, v in line_results.items()
                 if isinstance(lid, int) and lid not in merged_members]

        agg_tt   = sum(v["total_h"]    for v in valid)
        agg_lt   = sum(v["loading_h"]  for v in valid)
        agg_ot   = sum(v["operating_h"]for v in valid)
        agg_sd   = sum(v["sched_loss_h"]for v in valid)
        agg_nsd  = sum(v["op_loss_h"]  for v in valid)
        agg_tout = sum(v["actual_output"] for v in valid)
        agg_gout = sum(v["good_product"]  for v in valid)
        agg_act  = sum(v["actual_throughput"] for v in valid if v["std_throughput"] > 0)
        agg_stp  = sum(v["std_throughput"]    for v in valid if v["std_throughput"] > 0)

        # all_line shifts: sum across all non-merged lines
        all_shifts: dict = {}
        for sid in shift_id_list:
            as_sd  = sum(sched_h.get((bucket, lid, sid), 0.0) for lid in line_id_list if lid not in merged_members)
            as_nsd = sum(op_h.get((bucket, lid, sid), 0.0)    for lid in line_id_list if lid not in merged_members)
            as_tt  = tt * len([lid for lid in line_id_list if lid not in merged_members])
            as_lt  = max(0.0, round(as_tt - as_sd, 6))
            as_ot  = max(0.0, round(as_lt - as_nsd, 6))
            all_shifts[sid] = {
                "shift_name": shift_id_map[sid],
                "total_h": round(as_tt, 4), "sched_loss_h": round(as_sd, 4),
                "loading_h": round(as_lt, 4), "op_loss_h": round(as_nsd, 4), "operating_h": round(as_ot, 4),
            }

        # Aggregate breakdown all_line
        all_sbd: dict = {}
        all_obd: dict = {}
        for lid in line_id_list:
            if lid in merged_members:
                continue
            for sid in shift_id_list:
                k = (bucket, lid, sid)
                for lv, v in sched_bd.get(k, {}).items():
                    all_sbd[lv] = all_sbd.get(lv, 0.0) + v
                for lv, v in op_bd.get(k, {}).items():
                    all_obd[lv] = all_obd.get(lv, 0.0) + v

        all_avail = _safe_rate(agg_ot, agg_lt)
        all_perf  = _safe_rate(agg_act, agg_stp)
        all_qual  = _safe_rate(agg_gout, agg_tout)
        all_oee: Optional[float] = None
        if all_avail and all_perf and all_qual:
            all_oee = round(all_avail * all_perf * all_qual / 10_000, 2)

        results.append({
            "date":           bucket,
            "n_shifts":       len(shifts),
            "hours_per_shift":HOURS_PER_SHIFT,
            "lines":          line_results,
            "all_line": {
                "shifts":        all_shifts,
                "total_h":       round(agg_tt,  4),
                "sched_loss_h":  round(agg_sd,  4),
                "loading_h":     round(agg_lt,  4),
                "op_loss_h":     round(agg_nsd, 4),
                "operating_h":   round(agg_ot,  4),
                "actual_output": round(agg_tout,4),
                "good_product":  round(agg_gout,4),
                "availability":  all_avail,
                "performance":   all_perf,
                "quality":       all_qual,
                "oee":           all_oee,
                "sched_breakdown": [{"l1":lv[0],"l2":lv[1],"l3":lv[2],"hours":round(v,4)} for lv,v in sorted(all_sbd.items())],
                "op_breakdown":    [{"l1":lv[0],"l2":lv[1],"l3":lv[2],"hours":round(v,4)} for lv,v in sorted(all_obd.items())],
            },
        })

    return results
