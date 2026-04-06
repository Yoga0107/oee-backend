"""
app/oee/formulas.py
───────────────────
Semua formula kalkulasi OEE dikumpulkan di satu tempat.
Mudah dibaca, mudah ditest, mudah diextend.

Formula:
  loading_time   = total_time - Σ scheduled_downtime_losses
  operating_time = loading_time - Σ operating_losses
  availability   = operating_time / loading_time × 100

  ideal_output   = operating_time_h × standard_throughput  (unit/jam)
  performance    = actual_output / ideal_output × 100

  quality        = good_product / actual_output × 100

  all_line (availability / performance / quality):
    = Σ numerator_i / Σ denominator_i × 100
"""

from typing import Optional


# ─── Loading / Operating Time ─────────────────────────────────────────────────

def calc_shift_hours(time_from, time_to) -> float:
    """
    Hitung durasi shift dalam jam dari time object.
    Menangani shift lintas tengah malam (time_to < time_from).
    """
    from_m = time_from.hour * 60 + time_from.minute
    to_m   = time_to.hour   * 60 + time_to.minute
    diff   = (to_m - from_m) if to_m > from_m else (1440 - from_m + to_m)
    return round(diff / 60, 4)


def calc_loading_time(total_h: float, sched_loss_h: float) -> float:
    """loading_time = total_time - Σ scheduled_downtime"""
    return max(0.0, round(total_h - sched_loss_h, 4))


def calc_operating_time(loading_h: float, op_loss_h: float) -> float:
    """operating_time = loading_time - Σ operating_losses"""
    return max(0.0, round(loading_h - op_loss_h, 4))


def calc_availability(operating_h: float, loading_h: float) -> Optional[float]:
    """availability = operating_time / loading_time × 100"""
    if loading_h <= 0:
        return None
    return round(operating_h / loading_h * 100, 2)


def calc_all_line_rate(numerators: list[float], denominators: list[float]) -> Optional[float]:
    """
    Generic all-line aggregation:
      all_line = Σ numerator_i / Σ denominator_i × 100
    Dipakai untuk availability, performance, dan quality.
    """
    den = sum(denominators)
    if den <= 0:
        return None
    return round(sum(numerators) / den * 100, 2)


# ─── Performance Rate ─────────────────────────────────────────────────────────

def calc_ideal_output(operating_h: float, std_throughput: float) -> float:
    """
    ideal_output = operating_time (jam) × standard_throughput (unit/jam)
    std_throughput dalam unit/jam (konversi dari unit/shift jika perlu di caller).
    """
    return round(operating_h * std_throughput, 2)


def calc_performance(actual_output: float, ideal_output: float) -> Optional[float]:
    """
    performance = actual_output / ideal_output × 100
    Returns None jika ideal_output = 0.
    """
    if ideal_output <= 0:
        return None
    return round(min(actual_output / ideal_output * 100, 100.0), 2)


# ─── Quality Rate ─────────────────────────────────────────────────────────────

def calc_quality(good_product: float, actual_output: float) -> Optional[float]:
    """
    quality = good_product / actual_output × 100
    Returns None jika actual_output = 0.
    """
    if actual_output <= 0:
        return None
    return round(good_product / actual_output * 100, 2)
