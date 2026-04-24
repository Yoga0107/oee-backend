"""
app/oee/formulas.py
───────────────────
Semua formula OEE — implementasi dari measurement.ipynb menggunakan polars.

Pipeline kalkulasi:
  total_time      = shift_hours × jumlah hari aktif
  loading_time    = total_time - scheduled_downtime
  operating_time  = loading_time - not_scheduled_downtime (operating losses)
  availability    = operating_time / loading_time × 100

  actual_throughput = total_output / operating_time
  std_throughput    = std_output / final_operating_time  (dari master)
  performance       = actual_throughput / std_throughput × 100

  quality           = finished_goods / total_output × 100

  OEE               = (availability × performance × quality) / 10000

Kategori loss:
  - Scheduled Downtime  : L1 name = 'Scheduled Downtime'
  - Operating Losses    : semua L1 selain Scheduled, Performance Loss, Defects & Rework Loss
  - Good Product        : output_type dengan is_good_product = True
"""

from typing import Optional
import polars as pl

# ─── Konstanta ────────────────────────────────────────────────────────────────

SCHEDULED_L1      = "Scheduled Downtime"
PERFORMANCE_L1    = "Performance Loss"
DEFECT_L1         = "Defects & Rework Loss"
NON_OPERATING_L1s = {SCHEDULED_L1, PERFORMANCE_L1, DEFECT_L1}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _calc_shift_hours(time_from, time_to) -> float:
    """Durasi shift dalam jam, menangani lintas tengah malam."""
    from_m = time_from.hour * 60 + time_from.minute
    to_m   = time_to.hour   * 60 + time_to.minute
    diff   = (to_m - from_m) if to_m > from_m else (1440 - from_m + to_m)
    return round(diff / 60, 4)


def _safe_rate(numerator: float, denominator: float) -> Optional[float]:
    """Hitung rate %, return None jika denominator = 0."""
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 2)


def _all_line_rate(nums: list[float], dens: list[float]) -> Optional[float]:
    """all_line = Σ numerator / Σ denominator × 100 (formula notebook)."""
    d = sum(dens)
    if d <= 0:
        return None
    return round(sum(nums) / d * 100, 2)


# ─── Core pipeline (satu fungsi, semua metrik) ───────────────────────────────

def compute_oee_metrics(
    *,
    # Master data
    lines:           list[dict],   # [{id, name}]
    shifts:          list[dict],   # [{id, name, time_from, time_to}]
    merged_lines:    list[dict],   # [{name, member_ids: [line_id, ...]}]
    std_throughputs: list[dict],   # [{line_id, feed_code_id, std_output, final_op_time}]
    # Transaksional
    loss_inputs:     list[dict],   # [{line_id, shift_id, duration_min, l1_name, is_scheduled}]
    prod_outputs:    list[dict],   # [{line_id, shift_id, quantity, is_good_product}]
    # Config
    active_days:     dict[int, set],  # {line_id: set of date}
    date_from,
    date_to,
    group_by:        str = "daily",
) -> list[dict]:
    """
    Implementasi pipeline dari measurement.ipynb.

    Returns list of bucket dict per (date/month):
    {
      "date":     str,
      "lines":    {line_id: {...metrics...}},
      "all_line": {...aggregated metrics...}
    }
    """
    # total shift hours
    total_shift_h = sum(_calc_shift_hours(s["time_from"], s["time_to"]) for s in shifts)
    shift_id_map  = {s["id"]: s["name"] for s in shifts}
    line_id_map   = {l["id"]: l["name"] for l in lines}
    line_id_list  = [l["id"] for l in lines]

    # Merged line: {merged_name: [member_line_ids]}
    ml_map: dict[str, list[int]] = {m["name"]: m["member_ids"] for m in merged_lines}
    # Individual lines yang termasuk dalam merged (exclude from direct rate)
    merged_members: set[int] = {lid for m in merged_lines for lid in m["member_ids"]}

    # ── Standard throughput per line ─────────────────────────────────────────
    # std_throughput[line_id] = std_output / final_operating_time  (weighted avg)
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

    # ── Bucket function ───────────────────────────────────────────────────────
    from datetime import date as dt_date, datetime, timedelta

    def bk(d) -> str:
        dd = d.date() if isinstance(d, datetime) else d
        return dd.strftime("%Y-%m") if group_by == "monthly" else dd.strftime("%Y-%m-%d")

    # ── total_time per (bucket, line_id) ─────────────────────────────────────
    total_h: dict[str, dict[int, float]] = {}
    for lid, days in active_days.items():
        for d in days:
            dd = d.date() if isinstance(d, datetime) else d
            if dd < date_from or dd > date_to:
                continue
            bucket = bk(dd)
            total_h.setdefault(bucket, {})
            total_h[bucket][lid] = total_h[bucket].get(lid, 0.0) + total_shift_h

    # ── Aggregate losses per (bucket, line_id) ────────────────────────────────
    sched_h: dict[str, dict[int, float]] = {}   # scheduled downtime
    op_h:    dict[str, dict[int, float]] = {}   # operating losses (not-scheduled)

    for row in loss_inputs:
        bucket = bk(row["date"])
        lid    = row["line_id"]
        dur_h  = float(row["duration_min"] or 0) / 60
        if row["is_scheduled"]:
            sched_h.setdefault(bucket, {})
            sched_h[bucket][lid] = sched_h[bucket].get(lid, 0.0) + dur_h
        else:
            op_h.setdefault(bucket, {})
            op_h[bucket][lid] = op_h[bucket].get(lid, 0.0) + dur_h

    # ── Aggregate output per (bucket, line_id) ────────────────────────────────
    total_out:  dict[str, dict[int, float]] = {}  # semua output
    good_out:   dict[str, dict[int, float]] = {}  # finished goods saja

    for row in prod_outputs:
        bucket = bk(row["date"])
        lid    = row["line_id"]
        qty    = float(row["quantity"] or 0)
        total_out.setdefault(bucket, {})
        total_out[bucket][lid] = total_out[bucket].get(lid, 0.0) + qty
        if row["is_good_product"]:
            good_out.setdefault(bucket, {})
            good_out[bucket][lid] = good_out[bucket].get(lid, 0.0) + qty

    # ── Semua buckets yang relevan ────────────────────────────────────────────
    all_buckets = sorted(
        set(total_h) | set(sched_h) | set(op_h) | set(total_out)
    )

    results = []

    for bucket in all_buckets:
        line_results: dict[int, dict] = {}

        # ── Per individual line ──────────────────────────────────────────────
        for lid in line_id_list:
            tt   = total_h.get(bucket, {}).get(lid, 0.0)
            sd   = sched_h.get(bucket, {}).get(lid, 0.0)
            nsd  = op_h.get(bucket, {}).get(lid, 0.0)
            tout = total_out.get(bucket, {}).get(lid, 0.0)
            gout = good_out.get(bucket, {}).get(lid, 0.0)
            stp  = std_tp.get(lid, 0.0)

            lt   = max(0.0, round(tt   - sd,  4))   # loading_time
            ot   = max(0.0, round(lt   - nsd, 4))   # operating_time

            avail = _safe_rate(ot, lt)
            act_tp = round(tout / ot, 4) if ot > 0 else 0.0
            perf  = _safe_rate(act_tp, stp) if stp > 0 and lid not in merged_members else None
            qual  = _safe_rate(gout, tout)  if lid not in merged_members else None

            oee: Optional[float] = None
            if avail is not None and perf is not None and qual is not None:
                oee = round(avail * perf * qual / 10000, 2)

            line_results[lid] = {
                "name":          line_id_map[lid],
                "total_h":       round(tt,   4),
                "sched_loss_h":  round(sd,   4),
                "op_loss_h":     round(nsd,  4),
                "loading_h":     lt,
                "operating_h":   ot,
                "actual_output": tout,
                "good_product":  gout,
                "std_throughput": stp,
                "actual_throughput": act_tp,
                "availability":  avail,
                "performance":   perf,
                "quality":       qual,
                "oee":           oee,
            }

        # ── Merged lines ─────────────────────────────────────────────────────
        for ml_name, member_ids in ml_map.items():
            # Sum dari member lines
            ml_tt   = sum(line_results.get(lid, {}).get("total_h",       0) for lid in member_ids)
            ml_sd   = sum(line_results.get(lid, {}).get("sched_loss_h",  0) for lid in member_ids)
            ml_nsd  = sum(line_results.get(lid, {}).get("op_loss_h",     0) for lid in member_ids)
            ml_lt   = sum(line_results.get(lid, {}).get("loading_h",     0) for lid in member_ids)
            ml_ot   = sum(line_results.get(lid, {}).get("operating_h",   0) for lid in member_ids)
            ml_tout = sum(line_results.get(lid, {}).get("actual_output", 0) for lid in member_ids)
            ml_gout = sum(line_results.get(lid, {}).get("good_product",  0) for lid in member_ids)
            # std_throughput merged = sum of members
            ml_stp  = sum(std_tp.get(lid, 0.0) for lid in member_ids)
            ml_act_tp = round(ml_tout / ml_ot, 4) if ml_ot > 0 else 0.0
            ml_avail  = _safe_rate(ml_ot, ml_lt)
            # Merged line tidak punya performance/quality sendiri (notebook: excluded)
            line_results[ml_name] = {  # type: ignore[index]
                "name":          ml_name,
                "total_h":       round(ml_tt,  4),
                "sched_loss_h":  round(ml_sd,  4),
                "op_loss_h":     round(ml_nsd, 4),
                "loading_h":     round(ml_lt,  4),
                "operating_h":   round(ml_ot,  4),
                "actual_output": ml_tout,
                "good_product":  ml_gout,
                "std_throughput": ml_stp,
                "actual_throughput": ml_act_tp,
                "availability":  ml_avail,
                "performance":   None,
                "quality":       None,
                "oee":           None,
            }

        # ── all_line aggregate (hanya non-merged members) ─────────────────────
        valid = [v for lid, v in line_results.items()
                 if isinstance(lid, int) and lid not in merged_members]

        agg_lt  = [v["loading_h"]   for v in valid if v["loading_h"]   > 0]
        agg_ot  = [v["operating_h"] for v in valid if v["loading_h"]   > 0]
        agg_stp = [v["std_throughput"] for v in valid if v["std_throughput"] > 0]
        agg_act = [v["actual_throughput"] for v in valid if v["std_throughput"] > 0]
        agg_tout= [v["actual_output"] for v in valid]
        agg_gout= [v["good_product"]  for v in valid]

        all_avail = _all_line_rate(agg_ot,  agg_lt)
        all_perf  = _all_line_rate(agg_act, agg_stp)
        all_qual  = _all_line_rate(agg_gout, agg_tout) if sum(agg_tout) > 0 else None
        all_oee: Optional[float] = None
        if all_avail and all_perf and all_qual:
            all_oee = round(all_avail * all_perf * all_qual / 10000, 2)

        results.append({
            "date":    bucket,
            "lines":   line_results,
            "all_line": {
                "total_h":       round(sum(v["total_h"]     for v in valid), 4),
                "loading_h":     round(sum(agg_lt),  4),
                "operating_h":   round(sum(agg_ot),  4),
                "actual_output": sum(agg_tout),
                "good_product":  sum(agg_gout),
                "availability":  all_avail,
                "performance":   all_perf,
                "quality":       all_qual,
                "oee":           all_oee,
            },
        })

    return results
