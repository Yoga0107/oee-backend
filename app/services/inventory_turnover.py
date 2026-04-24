"""
app/services/inventory_turnover.py
───────────────────────────────────
Business logic untuk Inventory Turnover
Menggunakan schema khusus: national_sc
"""

import calendar
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ─── SCHEMA HELPER ─────────────────────────────────────────

def _set_schema(db: Session):
    """Pastikan semua query pakai schema national_sc"""
    db.execute(text("SET search_path TO national_sc, public"))


# ─── HELPERS ───────────────────────────────────────────────

def _to_title_case(s: str) -> str:
    return s.title() if s else ""


def _calculate_turnover(rows: list[dict], bu_filter: Optional[str] = None) -> float:
    data = rows
    if bu_filter:
        key = bu_filter.lower()
        data = [r for r in rows if (r.get("business_unit") or "").lower() == key]
    if not data:
        return 0.0
    sum_p     = sum(float(r.get("pemakaian") or 0) for r in data)
    sum_avg_s = sum(float(r.get("avg_saldo") or 0) for r in data)
    return round(sum_p / sum_avg_s, 1) if sum_avg_s else 0.0


def _calculate_doi(rows: list[dict], bu_filter: Optional[str] = None) -> float:
    data = rows
    if bu_filter:
        key = bu_filter.lower()
        data = [r for r in rows if (r.get("business_unit") or "").lower() == key]
    if not data:
        return 0.0
    sum_p     = sum(float(r.get("pemakaian") or 0) for r in data)
    sum_avg_s = sum(float(r.get("avg_saldo") or 0) for r in data)
    unique_ym = {(int(r["year"]), int(r["month"])) for r in data if r.get("year") and r.get("month")}
    total_days = sum(calendar.monthrange(y, m)[1] for y, m in unique_ym)
    if not total_days or not sum_p:
        return 0.0
    return round((sum_avg_s / sum_p) * total_days, 0)


# ─── RAW DATA ──────────────────────────────────────────────

def _get_raw_data(db: Session, year: int, months: list[int], plants: list[str]) -> list[dict]:
    _set_schema(db)

    month_clause = ""
    plant_clause = ""
    params: dict = {"year": year}

    if months:
        month_clause = "AND month = ANY(:months)"
        params["months"] = months

    if plants:
        plant_clause = "AND plant = ANY(:plants)"
        params["plants"] = plants

    sql = text(f"""
        SELECT year, month, plant, business_unit, material_code,
               saldo_awal, penerimaan, pemakaian, saldo_akhir,
               avg_saldo, turnover, days_of_inventory
        FROM inventory_turnover
        WHERE year = :year
        {month_clause}
        {plant_clause}
    """)

    result = db.execute(sql, params)
    return [dict(row._mapping) for row in result]


# ─── FILTER ────────────────────────────────────────────────

def get_filter_options(db: Session) -> dict:
    _set_schema(db)

    years  = db.execute(text("SELECT DISTINCT year FROM inventory_turnover ORDER BY year DESC")).fetchall()
    plants = db.execute(text("SELECT DISTINCT plant FROM inventory_turnover ORDER BY plant ASC")).fetchall()
    bus    = db.execute(text("SELECT DISTINCT business_unit FROM inventory_turnover ORDER BY business_unit ASC")).fetchall()

    return {
        "year":          [r[0] for r in years],
        "plants":        [r[0] for r in plants],
        "business_unit": [r[0] for r in bus],
        "months":        [{"id": i + 1, "name": n} for i, n in enumerate(MONTH_NAMES)],
    }


def get_latest_month(db: Session, year: int) -> Optional[int]:
    _set_schema(db)

    row = db.execute(
        text("SELECT MAX(month) FROM inventory_turnover WHERE year = :year"),
        {"year": year},
    ).scalar()

    return int(row) if row else None


# ─── DASHBOARD ─────────────────────────────────────────────

def get_dashboard_summary(
    db: Session,
    year: int,
    months: list[int],
    plants: list[str],
) -> dict:

    raw = _get_raw_data(db, year, months, plants)
    current_month = max(months) if months else (get_latest_month(db, year) or 1)

    monthly_trend = []
    for idx, name in enumerate(SHORT_MONTHS):
        m_num = idx + 1
        m_data = [r for r in raw if int(r.get("month") or 0) == m_num]
        sum_p = sum(float(r.get("pemakaian") or 0) for r in m_data)
        sum_s = sum(float(r.get("avg_saldo") or 0) for r in m_data)
        monthly_trend.append({
            "month": name,
            "overallTurnover": round(sum_p / sum_s, 1) if sum_s else 0.0
        })

    plant_names = sorted({r["plant"] for r in raw if r.get("plant")})

    plant_comparison = [
        {
            "plant": p,
            "overallTurnover": _calculate_turnover([r for r in raw if r["plant"] == p]),
            "fishTurnover": _calculate_turnover([r for r in raw if r["plant"] == p], "fish"),
            "shrimpTurnover": _calculate_turnover([r for r in raw if r["plant"] == p], "shrimp"),
        }
        for p in plant_names
    ]

    return {
        "overallTurnover": _calculate_turnover(raw),
        "fishTurnover": _calculate_turnover(raw, "fish"),
        "shrimpTurnover": _calculate_turnover(raw, "shrimp"),
        "overallDOI": _calculate_doi(raw),
        "monthlyTrend": monthly_trend,
        "plantComparison": plant_comparison,
        "currentMonth": current_month,
    }


# ─── TREND ────────────────────────────────────────────────

def get_trend_analysis(db: Session, year: int, months: list[int]) -> list[dict]:
    _set_schema(db)

    month_clause = "AND month = ANY(:months)" if months else ""
    params: dict = {"year": year}

    if months:
        params["months"] = months

    rows = db.execute(text(f"""
        SELECT year, month, overall_turnover, fish_turnover,
               shrimp_turnover, best_performing, worst_performing
        FROM it_trend_analysis_monthly
        WHERE year = :year {month_clause}
        ORDER BY month ASC
    """), params).fetchall()

    result = []
    for r in rows:
        m = int(r[1]) if r[1] else 0
        result.append({
            "year": int(r[0] or year),
            "month": MONTH_NAMES[m - 1] if 1 <= m <= 12 else "Unknown",
            "overallTurnover": float(r[2] or 0),
            "fishTurnover": float(r[3] or 0),
            "shrimpTurnover": float(r[4] or 0),
            "bestPerforming": r[5] or "-",
            "worstPerforming": r[6] or "-",
        })

    return result


# ─── PERFORMANCE (FIXED) ───────────────────────────────────

def get_monthly_performance(
    db: Session, year: int, plants: list[str], business_unit: list[str]
) -> list[dict]:

    _set_schema(db)

    plant_clause = "AND plant = ANY(:plants)" if plants else ""
    bu_clause    = "AND business_unit = ANY(:bus)" if business_unit else ""

    params: dict = {"year": year}
    if plants:
        params["plants"] = plants
    if business_unit:
        params["bus"] = business_unit

    rows = db.execute(text(f"""
        SELECT plant, business_unit, year,
               jan, feb, mar, apr, may, jun,
               jul, aug, sep, oct, nov, dec,
               inventory_turnover_ytd
        FROM it_plant_performance_detail_monthly
        WHERE year = :year {plant_clause} {bu_clause}
        ORDER BY plant ASC, business_unit ASC
    """), params).fetchall()

    keys = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]

    result = []
    for r in rows:
        r = dict(r._mapping)
        result.append({
            "plant": r.get("plant") or "Unknown",
            "businessUnit": r.get("business_unit") or "N/A",
            "year": int(r.get("year") or year),
            "monthlyData": [
                {"month": SHORT_MONTHS[i], "value": float(r.get(k) or 0)}
                for i, k in enumerate(keys)
            ],
            "inventory_turnover_ytd": float(r.get("inventory_turnover_ytd") or 0),
        })

    return result