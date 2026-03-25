"""
input.py
────────
Endpoint untuk input data transaksional OEE:
  - Production Output (produksi harian per shift per line)
  - Machine Loss Input

URL prefix: /api/v1/input

Features:
  - Export to Excel (roles: administrator, plant_manager, operator)
  - Import from Excel (roles: administrator, plant_manager only)
"""

import io
from datetime import datetime as dt

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.db.database import get_plant_db
from app.core.deps import CurrentUser, CurrentPlant
from app.models.plant_schema import (
    ProductionOutput, ProductionOutputItem,
    MachineLossInput, MachineLoss,
    MasterLine, MasterShift, MasterFeedCode,
)
from app.schemas.input import (
    ProductionOutputCreate, ProductionOutputUpdate, ProductionOutputResponse,
    MachineLossInputCreate, MachineLossInputUpdate, MachineLossInputResponse,
)

router = APIRouter(prefix="/input", tags=["Input Data"])

EXPORT_ROLES = {"administrator", "plant_manager", "operator"}
IMPORT_ROLES = {"administrator", "plant_manager"}


def _assert_role(user, allowed_roles: set, action: str = "action"):
    role_name = user.role.name if user.role else ""
    if not user.is_superuser and role_name not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Akses ditolak: {action} hanya untuk {', '.join(sorted(allowed_roles))}",
        )


def _db(plant: CurrentPlant) -> Session:
    return next(get_plant_db(plant.schema_name))


def _compute_derived(fg, dg, wip, remix, rej):
    actual = fg + dg + wip + remix + rej
    good = fg
    qr = round((good / actual * 100), 2) if actual > 0 else 0.0
    return actual, good, qr


def _sync_output_items(db, item: ProductionOutput):
    """
    Sync the production_output_items child rows to match the 5 quantity fields
    on the parent ProductionOutput. Called after every create/update.
    Creates items that don't exist; updates quantities; deletes stale rows.
    """
    type_qty = {
        "finished_goods":     item.finished_goods,
        "downgraded_product": item.downgraded_product,
        "wip":                item.wip,
        "remix":              item.remix,
        "reject_product":     item.reject_product,
    }
    existing = {i.output_type: i for i in item.items}
    for otype, qty in type_qty.items():
        if otype in existing:
            existing[otype].quantity = qty
        else:
            db.add(ProductionOutputItem(output_id=item.id, output_type=otype, quantity=qty))
    # Remove any orphan types (shouldn't happen, but safety)
    for otype, row in existing.items():
        if otype not in type_qty:
            db.delete(row)


def _build_output_response(item):
    return {
        "id": item.id, "date": item.date,
        "line_id": item.line_id, "shift_id": item.shift_id,
        "feed_code_id": item.feed_code_id, "production_plan": item.production_plan,
        "finished_goods": item.finished_goods, "downgraded_product": item.downgraded_product,
        "wip": item.wip, "remix": item.remix, "reject_product": item.reject_product,
        "actual_output": item.actual_output, "good_product": item.good_product,
        "quality_rate": item.quality_rate, "remarks": item.remarks,
        "is_active": item.is_active, "created_at": item.created_at,
        "created_by_id": item.created_by_id,
        "line_name": item.line.name if item.line else None,
        "shift_name": item.shift.name if item.shift else None,
        "feed_code_code": item.feed_code.code if item.feed_code else None,
    }


def _build_loss_response(item):
    return {
        "id": item.id, "date": item.date,
        "line_id": item.line_id, "shift_id": item.shift_id,
        "feed_code_id": item.feed_code_id,
        "loss_l1_id": item.loss_l1_id, "loss_l2_id": item.loss_l2_id, "loss_l3_id": item.loss_l3_id,
        "time_from": item.time_from, "time_to": item.time_to,
        "duration_minutes": item.duration_minutes, "remarks": item.remarks,
        "is_active": item.is_active, "created_at": item.created_at,
        "created_by_id": item.created_by_id,
        "line_name": item.line.name if item.line else None,
        "shift_name": item.shift.name if item.shift else None,
        "feed_code_code": item.feed_code.code if item.feed_code else None,
        "loss_l1_name": item.loss_l1.name if item.loss_l1 else None,
        "loss_l2_name": item.loss_l2.name if item.loss_l2 else None,
        "loss_l3_name": item.loss_l3.name if item.loss_l3 else None,
    }


def _validate_loss_refs(db, d):
    if d.get("line_id"):
        if not db.query(MasterLine).filter(MasterLine.id == d["line_id"], MasterLine.is_active == True).first():
            raise HTTPException(404, "Line not found")
    if d.get("shift_id"):
        if not db.query(MasterShift).filter(MasterShift.id == d["shift_id"], MasterShift.is_active == True).first():
            raise HTTPException(404, "Shift not found")
    if d.get("feed_code_id"):
        if not db.query(MasterFeedCode).filter(MasterFeedCode.id == d["feed_code_id"], MasterFeedCode.is_active == True).first():
            raise HTTPException(404, "Feed code not found")
    for field, level in [("loss_l1_id", 1), ("loss_l2_id", 2), ("loss_l3_id", 3)]:
        if d.get(field):
            if not db.query(MachineLoss).filter(MachineLoss.id == d[field], MachineLoss.level == level, MachineLoss.is_active == True).first():
                raise HTTPException(404, f"Loss L{level} not found")


# ─── Excel style helpers ──────────────────────────────────────────────────────

def _border(style="thin"):
    s = Side(style=style, color="D1D5DB")
    return Border(left=s, right=s, top=s, bottom=s)


def _hdr(cell, bg, fc="FFFFFF"):
    cell.fill = PatternFill("solid", fgColor=bg)
    cell.font = Font(bold=True, color=fc, size=10, name="Calibri")
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell.border = _border("medium")


def _data(cell, row_i, numfmt=None, center=False):
    bg = "F8FAFC" if row_i % 2 == 0 else "FFFFFF"
    cell.fill = PatternFill("solid", fgColor=bg)
    cell.font = Font(size=9, name="Calibri")
    cell.alignment = Alignment(horizontal="center" if center else "left", vertical="center")
    cell.border = _border()
    if numfmt:
        cell.number_format = numfmt


def _title_rows(ws, title, ncols, bg):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(row=1, column=1, value=title)
    c.fill = PatternFill("solid", fgColor=bg)
    c.font = Font(bold=True, color="FFFFFF", size=14, name="Calibri")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 34

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    c2 = ws.cell(row=2, column=1, value=f"Generated: {dt.now().strftime('%d %B %Y  %H:%M')}")
    c2.fill = PatternFill("solid", fgColor="1E3A5F")
    c2.font = Font(color="BFD7FF", size=9, italic=True, name="Calibri")
    c2.alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[2].height = 18


# ════════════════════════════════════════════════════════
# PRODUCTION OUTPUTS – CRUD
# ════════════════════════════════════════════════════════

@router.get("/production-outputs", response_model=list[ProductionOutputResponse])
def list_production_outputs(current_user: CurrentUser, plant: CurrentPlant,
    date_from: str | None = None, date_to: str | None = None,
    line_id: int | None = None, shift_id: int | None = None):
    db = _db(plant)
    q = db.query(ProductionOutput).filter(ProductionOutput.is_active == True)
    if date_from: q = q.filter(ProductionOutput.date >= dt.fromisoformat(date_from))
    if date_to:   q = q.filter(ProductionOutput.date <= dt.fromisoformat(date_to + "T23:59:59"))
    if line_id:   q = q.filter(ProductionOutput.line_id == line_id)
    if shift_id:  q = q.filter(ProductionOutput.shift_id == shift_id)
    return [_build_output_response(i) for i in q.order_by(ProductionOutput.date.desc(), ProductionOutput.id.desc()).all()]


@router.post("/production-outputs", response_model=ProductionOutputResponse, status_code=201)
def create_production_output(payload: ProductionOutputCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if not db.query(MasterLine).filter(MasterLine.id == payload.line_id, MasterLine.is_active == True).first():
        raise HTTPException(404, "Line tidak ditemukan")
    if not db.query(MasterShift).filter(MasterShift.id == payload.shift_id, MasterShift.is_active == True).first():
        raise HTTPException(404, "Shift tidak ditemukan")
    if payload.feed_code_id:
        if not db.query(MasterFeedCode).filter(MasterFeedCode.id == payload.feed_code_id, MasterFeedCode.is_active == True).first():
            raise HTTPException(404, "Kode pakan tidak ditemukan")
    actual, good, qr = _compute_derived(payload.finished_goods, payload.downgraded_product, payload.wip, payload.remix, payload.reject_product)
    item = ProductionOutput(date=payload.date, line_id=payload.line_id, shift_id=payload.shift_id,
        feed_code_id=payload.feed_code_id, production_plan=payload.production_plan,
        finished_goods=payload.finished_goods, downgraded_product=payload.downgraded_product,
        wip=payload.wip, remix=payload.remix, reject_product=payload.reject_product,
        actual_output=actual, good_product=good, quality_rate=qr,
        remarks=payload.remarks, created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    _sync_output_items(db, item)
    db.commit(); db.refresh(item)
    return _build_output_response(item)


@router.put("/production-outputs/{item_id}", response_model=ProductionOutputResponse)
def update_production_output(item_id: int, payload: ProductionOutputUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(ProductionOutput).filter(ProductionOutput.id == item_id, ProductionOutput.is_active == True).first()
    if not item: raise HTTPException(404, "Production output tidak ditemukan")
    data = payload.model_dump(exclude_none=True)
    if "line_id" in data and not db.query(MasterLine).filter(MasterLine.id == data["line_id"], MasterLine.is_active == True).first():
        raise HTTPException(404, "Line tidak ditemukan")
    if "shift_id" in data and not db.query(MasterShift).filter(MasterShift.id == data["shift_id"], MasterShift.is_active == True).first():
        raise HTTPException(404, "Shift tidak ditemukan")
    if "feed_code_id" in data and data["feed_code_id"]:
        if not db.query(MasterFeedCode).filter(MasterFeedCode.id == data["feed_code_id"], MasterFeedCode.is_active == True).first():
            raise HTTPException(404, "Kode pakan tidak ditemukan")
    for k, v in data.items(): setattr(item, k, v)
    actual, good, qr = _compute_derived(item.finished_goods, item.downgraded_product, item.wip, item.remix, item.reject_product)
    item.actual_output = actual; item.good_product = good; item.quality_rate = qr; item.updated_by_id = current_user.id
    db.commit(); db.refresh(item)
    _sync_output_items(db, item)
    db.commit(); db.refresh(item)
    return _build_output_response(item)


@router.delete("/production-outputs/{item_id}", status_code=204)
def delete_production_output(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(ProductionOutput).filter(ProductionOutput.id == item_id).first()
    if not item: raise HTTPException(404, "Production output tidak ditemukan")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


@router.get("/production-outputs/by-type", response_model=list[dict])
def list_output_by_type(
    current_user: CurrentUser,
    plant: CurrentPlant,
    date_from: str | None = None,
    date_to:   str | None = None,
    line_id:   int | None = None,
    shift_id:  int | None = None,
    output_type: str | None = None,
):
    """
    Return production output broken down by type (finished_goods, downgraded_product, etc.).
    Each row is one type entry from production_output_items joined with its parent.
    """
    from sqlalchemy import text as sqla_text
    db = _db(plant)
    q = (
        db.query(ProductionOutputItem, ProductionOutput)
        .join(ProductionOutput, ProductionOutputItem.output_id == ProductionOutput.id)
        .filter(ProductionOutput.is_active == True)
    )
    if date_from: q = q.filter(ProductionOutput.date >= dt.fromisoformat(date_from))
    if date_to:   q = q.filter(ProductionOutput.date <= dt.fromisoformat(date_to + "T23:59:59"))
    if line_id:   q = q.filter(ProductionOutput.line_id == line_id)
    if shift_id:  q = q.filter(ProductionOutput.shift_id == shift_id)
    if output_type: q = q.filter(ProductionOutputItem.output_type == output_type)

    rows = q.order_by(ProductionOutput.date.desc(), ProductionOutput.id.desc()).all()
    result = []
    for item_row, parent in rows:
        result.append({
            "item_id":     item_row.id,
            "output_id":   parent.id,
            "date":        parent.date,
            "line_id":     parent.line_id,
            "line_name":   parent.line.name if parent.line else None,
            "shift_id":    parent.shift_id,
            "shift_name":  parent.shift.name if parent.shift else None,
            "feed_code_id":   parent.feed_code_id,
            "feed_code_code": parent.feed_code.code if parent.feed_code else None,
            "output_type": item_row.output_type,
            "quantity":    item_row.quantity,
            "remarks":     parent.remarks,
        })
    return result


# ════════════════════════════════════════════════════════
# PRODUCTION OUTPUTS – EXPORT
# ════════════════════════════════════════════════════════

@router.get("/production-outputs/export")
def export_production_outputs(current_user: CurrentUser, plant: CurrentPlant,
    date_from: str | None = None, date_to: str | None = None,
    line_id: int | None = None, shift_id: int | None = None):
    """Export Production Outputs to Excel. Roles: administrator, plant_manager, operator."""
    _assert_role(current_user, EXPORT_ROLES, "Export Production Output")

    db = _db(plant)
    q = db.query(ProductionOutput).filter(ProductionOutput.is_active == True)
    if date_from: q = q.filter(ProductionOutput.date >= dt.fromisoformat(date_from))
    if date_to:   q = q.filter(ProductionOutput.date <= dt.fromisoformat(date_to + "T23:59:59"))
    if line_id:   q = q.filter(ProductionOutput.line_id == line_id)
    if shift_id:  q = q.filter(ProductionOutput.shift_id == shift_id)
    items = q.order_by(ProductionOutput.date.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Production Output"
    NCOLS = 15

    _title_rows(ws, f"Production Output  |  {plant.name}", NCOLS, "1D4ED8")

    # KPI strip (row 3)
    total_plan   = sum(i.production_plan or 0 for i in items)
    total_actual = sum(i.actual_output   or 0 for i in items)
    total_fg     = sum(i.finished_goods  or 0 for i in items)
    avg_q        = round(total_fg / total_actual * 100, 2) if total_actual else 0
    ws.row_dimensions[3].height = 46

    for idx, (lbl, val) in enumerate([
        ("Total Records", len(items)), ("Plan (kg)", f"{total_plan:,}"),
        ("Actual (kg)", f"{total_actual:,}"), ("Good Product", f"{total_fg:,}"), ("Avg Quality", f"{avg_q}%")
    ]):
        cs = idx * 3 + 1
        ws.merge_cells(start_row=3, start_column=cs, end_row=3, end_column=cs + 2)
        c = ws.cell(row=3, column=cs, value=f"{lbl}\n{val}")
        c.fill = PatternFill("solid", fgColor="DBEAFE")
        c.font = Font(bold=True, color="1D4ED8", size=10, name="Calibri")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _border("medium")

    ws.row_dimensions[4].height = 6

    COLS = [("No",5),("Tanggal",14),("Line",16),("Shift",12),("Kode Pakan",14),
            ("Plan (kg)",12),("FG (kg)",12),("DG (kg)",12),("WIP (kg)",12),
            ("Remix (kg)",12),("Reject (kg)",12),("Actual (kg)",12),
            ("Good Prod",12),("Quality %",12),("Remarks",24)]
    ws.row_dimensions[5].height = 30
    for ci, (h, w) in enumerate(COLS, 1):
        c = ws.cell(row=5, column=ci, value=h); _hdr(c, "3B82F6")
        ws.column_dimensions[get_column_letter(ci)].width = w

    for ri, item in enumerate(items, 1):
        r = ri + 5; ws.row_dimensions[r].height = 18
        qp = round(item.finished_goods / item.actual_output * 100, 2) if item.actual_output else 0
        row_vals = [ri, item.date.strftime("%d/%m/%Y") if item.date else "",
            item.line.name if item.line else "", item.shift.name if item.shift else "",
            item.feed_code.code if item.feed_code else "",
            item.production_plan or 0, item.finished_goods, item.downgraded_product,
            item.wip, item.remix, item.reject_product, item.actual_output,
            item.good_product, qp, item.remarks or ""]
        for ci, val in enumerate(row_vals, 1):
            c = ws.cell(row=r, column=ci, value=val)
            _data(c, ri, "#,##0" if 6 <= ci <= 13 else None, center=ci <= 5)
            if ci == 14:
                c.number_format = '0.00"%"'
                if qp >= 98:
                    c.fill = PatternFill("solid", fgColor="D1FAE5"); c.font = Font(color="065F46", bold=True, size=9, name="Calibri")
                elif qp >= 95:
                    c.fill = PatternFill("solid", fgColor="FEF9C3"); c.font = Font(color="713F12", bold=True, size=9, name="Calibri")
                else:
                    c.fill = PatternFill("solid", fgColor="FEE2E2"); c.font = Font(color="7F1D1D", bold=True, size=9, name="Calibri")

    # Import Template sheet
    ws2 = wb.create_sheet("Import Template")
    _title_rows(ws2, "Import Template  |  Production Output", 11, "059669")
    IH = [("date\n(YYYY-MM-DD)",18),("line_name",18),("shift_name",18),
          ("feed_code\n(opsional)",16),("production_plan\n(kg)",16),("finished_goods\n(kg)",16),
          ("downgraded_product\n(kg)",20),("wip\n(kg)",12),("remix\n(kg)",12),
          ("reject_product\n(kg)",16),("remarks\n(opsional)",24)]
    ws2.row_dimensions[3].height = 42
    for ci, (h, w) in enumerate(IH, 1):
        c = ws2.cell(row=3, column=ci, value=h); _hdr(c, "059669")
        ws2.column_dimensions[get_column_letter(ci)].width = w
    for ci, val in enumerate(["2025-01-15","LINE-01","Shift 1","P001",5000,4500,200,100,100,100,"Contoh data"], 1):
        c = ws2.cell(row=4, column=ci, value=val)
        c.fill = PatternFill("solid", fgColor="F0FDF4"); c.font = Font(size=9, italic=True, name="Calibri")
        c.alignment = Alignment(horizontal="center", vertical="center"); c.border = _border()

    # Instructions sheet
    ws3 = wb.create_sheet("Petunjuk Import")
    ws3.sheet_view.showGridLines = False
    ws3.column_dimensions["A"].width = 5; ws3.column_dimensions["B"].width = 65
    t = ws3.cell(row=1, column=1, value="Petunjuk Penggunaan Import — Production Output")
    t.font = Font(bold=True, size=13, color="1D4ED8", name="Calibri"); ws3.row_dimensions[1].height = 28
    for i, text in enumerate([
        "Gunakan sheet 'Import Template' sebagai format data import.",
        "Kolom date harus format YYYY-MM-DD (contoh: 2025-01-15).",
        "line_name harus sesuai nama Line yang terdaftar di master.",
        "shift_name harus sesuai nama Shift yang terdaftar di master.",
        "feed_code boleh dikosongkan jika tidak ada kode pakan.",
        "Semua kolom qty (kg) harus berupa angka >= 0.",
        "Kolom remarks bersifat opsional.",
        "Baris header (baris ke-3) JANGAN dihapus.",
        "Hapus baris contoh (baris 4) sebelum import jika tidak dipakai.",
        "File harus dalam format .xlsx sebelum diupload.",
    ], start=3):
        ws3.cell(row=i, column=1, value=f"{i-2}.").font = Font(bold=True, color="1D4ED8", size=10, name="Calibri")
        c = ws3.cell(row=i, column=2, value=text)
        c.font = Font(size=10, name="Calibri"); ws3.row_dimensions[i].height = 20

    ws.freeze_panes = "A6"; ws.sheet_view.showGridLines = False
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    fname = f"production_output_{plant.code}_{dt.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ════════════════════════════════════════════════════════
# PRODUCTION OUTPUTS – IMPORT
# ════════════════════════════════════════════════════════

@router.post("/production-outputs/import")
async def import_production_outputs(current_user: CurrentUser, plant: CurrentPlant, file: UploadFile = File(...)):
    """Import Production Outputs from Excel. Roles: administrator, plant_manager only."""
    _assert_role(current_user, IMPORT_ROLES, "Import Production Output")
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "File harus berformat .xlsx")
    contents = await file.read()
    try:
        wb = load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "File Excel tidak valid atau rusak")
    if "Import Template" not in wb.sheetnames:
        raise HTTPException(400, "Sheet 'Import Template' tidak ditemukan. Gunakan template yang disediakan.")

    ws = wb["Import Template"]
    db = _db(plant)
    lines  = {l.name.strip().lower(): l for l in db.query(MasterLine).filter(MasterLine.is_active == True).all()}
    shifts = {s.name.strip().lower(): s for s in db.query(MasterShift).filter(MasterShift.is_active == True).all()}
    fcodes = {f.code.strip().lower(): f for f in db.query(MasterFeedCode).filter(MasterFeedCode.is_active == True).all()}

    created, errors = 0, []
    for rn, row in enumerate(ws.iter_rows(min_row=4, values_only=True), start=4):
        if not any(row): continue
        cells = list(row) + [None]*11
        date_val, line_nm, shift_nm, fc_nm = cells[0], cells[1], cells[2], cells[3]
        plan, fg, dg, wip, remix, rej, remarks = cells[4], cells[5], cells[6], cells[7], cells[8], cells[9], cells[10]
        errs = []
        try:
            parsed_date = dt.fromisoformat(str(date_val).strip()) if isinstance(date_val, str) else dt.combine(date_val, dt.min.time())
        except:
            errs.append("format date salah"); parsed_date = None
        lo = lines.get((line_nm or "").strip().lower())
        so = shifts.get((shift_nm or "").strip().lower())
        if not lo: errs.append(f"line '{line_nm}' tidak ditemukan")
        if not so: errs.append(f"shift '{shift_nm}' tidak ditemukan")
        fco = fcodes.get(str(fc_nm or "").strip().lower()) if fc_nm else None
        if fc_nm and not fco: errs.append(f"kode pakan '{fc_nm}' tidak ditemukan")
        def si(v, lbl):
            try:
                x = int(float(v or 0))
                if x < 0: raise ValueError()
                return x
            except:
                errs.append(f"{lbl} harus angka >= 0"); return 0
        i_plan=si(plan,"production_plan"); i_fg=si(fg,"finished_goods"); i_dg=si(dg,"downgraded_product")
        i_wip=si(wip,"wip"); i_rmx=si(remix,"remix"); i_rej=si(rej,"reject_product")
        if errs: errors.append({"row": rn, "errors": errs}); continue
        actual, good, qr = _compute_derived(i_fg, i_dg, i_wip, i_rmx, i_rej)
        db.add(ProductionOutput(date=parsed_date, line_id=lo.id, shift_id=so.id,
            feed_code_id=fco.id if fco else None, production_plan=i_plan,
            finished_goods=i_fg, downgraded_product=i_dg, wip=i_wip, remix=i_rmx, reject_product=i_rej,
            actual_output=actual, good_product=good, quality_rate=qr,
            remarks=str(remarks).strip() if remarks else None, created_by_id=current_user.id))
        created += 1
    if created: db.commit()
    return {"imported": created, "errors": errors, "message": f"{created} baris berhasil diimport, {len(errors)} baris gagal."}


# ════════════════════════════════════════════════════════
# MACHINE LOSS INPUTS – CRUD
# ════════════════════════════════════════════════════════

@router.get("/machine-loss-inputs", response_model=list[MachineLossInputResponse])
def list_machine_loss_inputs(current_user: CurrentUser, plant: CurrentPlant,
    date_from: str | None = None, date_to: str | None = None,
    line_id: int | None = None, shift_id: int | None = None):
    db = _db(plant)
    q = db.query(MachineLossInput).filter(MachineLossInput.is_active == True)
    if date_from: q = q.filter(MachineLossInput.date >= dt.fromisoformat(date_from))
    if date_to:   q = q.filter(MachineLossInput.date <= dt.fromisoformat(date_to + "T23:59:59"))
    if line_id:   q = q.filter(MachineLossInput.line_id == line_id)
    if shift_id:  q = q.filter(MachineLossInput.shift_id == shift_id)
    return [_build_loss_response(i) for i in q.order_by(MachineLossInput.date.desc(), MachineLossInput.id.desc()).all()]


@router.post("/machine-loss-inputs", response_model=MachineLossInputResponse, status_code=201)
def create_machine_loss_input(payload: MachineLossInputCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant); _validate_loss_refs(db, payload.model_dump())
    item = MachineLossInput(date=payload.date, line_id=payload.line_id, shift_id=payload.shift_id,
        feed_code_id=payload.feed_code_id, loss_l1_id=payload.loss_l1_id,
        loss_l2_id=payload.loss_l2_id, loss_l3_id=payload.loss_l3_id,
        time_from=payload.time_from, time_to=payload.time_to,
        duration_minutes=payload.duration_minutes, remarks=payload.remarks, created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item); return _build_loss_response(item)


@router.put("/machine-loss-inputs/{item_id}", response_model=MachineLossInputResponse)
def update_machine_loss_input(item_id: int, payload: MachineLossInputUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossInput).filter(MachineLossInput.id == item_id, MachineLossInput.is_active == True).first()
    if not item: raise HTTPException(404, "Machine loss input not found")
    data = payload.model_dump(exclude_none=True); _validate_loss_refs(db, data)
    for k, v in data.items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item); return _build_loss_response(item)


@router.delete("/machine-loss-inputs/{item_id}", status_code=204)
def delete_machine_loss_input(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossInput).filter(MachineLossInput.id == item_id).first()
    if not item: raise HTTPException(404, "Machine loss input not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


# ════════════════════════════════════════════════════════
# MACHINE LOSS INPUTS – EXPORT
# ════════════════════════════════════════════════════════

@router.get("/machine-loss-inputs/export")
def export_machine_loss_inputs(current_user: CurrentUser, plant: CurrentPlant,
    date_from: str | None = None, date_to: str | None = None,
    line_id: int | None = None, shift_id: int | None = None):
    """Export Machine Loss Inputs to Excel. Roles: administrator, plant_manager, operator."""
    _assert_role(current_user, EXPORT_ROLES, "Export Machine Loss")

    db = _db(plant)
    q = db.query(MachineLossInput).filter(MachineLossInput.is_active == True)
    if date_from: q = q.filter(MachineLossInput.date >= dt.fromisoformat(date_from))
    if date_to:   q = q.filter(MachineLossInput.date <= dt.fromisoformat(date_to + "T23:59:59"))
    if line_id:   q = q.filter(MachineLossInput.line_id == line_id)
    if shift_id:  q = q.filter(MachineLossInput.shift_id == shift_id)
    items = q.order_by(MachineLossInput.date.desc()).all()

    wb = Workbook(); ws = wb.active; ws.title = "Machine Loss Input"
    NCOLS = 13; _title_rows(ws, f"Machine Loss Input  |  {plant.name}", NCOLS, "7C3AED")

    total_dur = sum(i.duration_minutes for i in items)
    ws.row_dimensions[3].height = 46
    for idx, (lbl, val) in enumerate([
        ("Total Records", len(items)),
        ("Total Durasi (min)", f"{round(total_dur,1):,}"),
        ("Total Durasi (h:m)", f"{int(total_dur//60)}h {int(total_dur%60)}m")
    ]):
        cs = idx * 4 + 1
        ws.merge_cells(start_row=3, start_column=cs, end_row=3, end_column=cs+3)
        c = ws.cell(row=3, column=cs, value=f"{lbl}\n{val}")
        c.fill = PatternFill("solid", fgColor="EDE9FE")
        c.font = Font(bold=True, color="6D28D9", size=10, name="Calibri")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _border("medium")

    ws.row_dimensions[4].height = 6
    COLS = [("No",4),("Tanggal",14),("Line",16),("Shift",12),("Kode Pakan",14),
            ("Loss L1",22),("Loss L2",22),("Loss L3",22),("Dari",8),("Sampai",8),
            ("Durasi (min)",14),("Durasi (h:m)",14),("Remarks",24)]
    ws.row_dimensions[5].height = 30
    for ci, (h, w) in enumerate(COLS, 1):
        c = ws.cell(row=5, column=ci, value=h); _hdr(c, "8B5CF6")
        ws.column_dimensions[get_column_letter(ci)].width = w

    for ri, item in enumerate(items, 1):
        r = ri + 5; ws.row_dimensions[r].height = 18
        dur = item.duration_minutes
        row_vals = [ri, item.date.strftime("%d/%m/%Y") if item.date else "",
            item.line.name if item.line else "", item.shift.name if item.shift else "",
            item.feed_code.code if item.feed_code else "",
            item.loss_l1.name if item.loss_l1 else "", item.loss_l2.name if item.loss_l2 else "",
            item.loss_l3.name if item.loss_l3 else "",
            item.time_from or "", item.time_to or "", dur,
            f"{int(dur//60)}h {int(dur%60):02d}m", item.remarks or ""]
        for ci, val in enumerate(row_vals, 1):
            c = ws.cell(row=r, column=ci, value=val)
            _data(c, ri, "#,##0.0" if ci == 11 else None, center=ci in {1,9,10,11,12})
            if ci == 11:
                if dur <= 30:
                    c.fill = PatternFill("solid", fgColor="D1FAE5"); c.font = Font(color="065F46", bold=True, size=9, name="Calibri")
                elif dur <= 120:
                    c.fill = PatternFill("solid", fgColor="FEF9C3"); c.font = Font(color="713F12", bold=True, size=9, name="Calibri")
                else:
                    c.fill = PatternFill("solid", fgColor="FEE2E2"); c.font = Font(color="7F1D1D", bold=True, size=9, name="Calibri")

    # Import Template sheet
    ws2 = wb.create_sheet("Import Template")
    _title_rows(ws2, "Import Template  |  Machine Loss Input", 11, "059669")
    IH = [("date\n(YYYY-MM-DD)",18),("line_name",18),("shift_name",18),
          ("feed_code\n(opsional)",16),("loss_l1_name\n(opsional)",22),
          ("loss_l2_name\n(opsional)",22),("loss_l3_name\n(opsional)",22),
          ("time_from\n(HH:MM)",16),("time_to\n(HH:MM)",16),
          ("duration_minutes\n(wajib, >0)",20),("remarks\n(opsional)",22)]
    ws2.row_dimensions[3].height = 42
    for ci, (h, w) in enumerate(IH, 1):
        c = ws2.cell(row=3, column=ci, value=h); _hdr(c, "059669")
        ws2.column_dimensions[get_column_letter(ci)].width = w
    for ci, val in enumerate(["2025-01-15","LINE-01","Shift 1","P001","Planned Stop","Changeover","Cleaning","08:00","09:30",90.0,"Ganti produk"], 1):
        c = ws2.cell(row=4, column=ci, value=val)
        c.fill = PatternFill("solid", fgColor="F0FDF4"); c.font = Font(size=9, italic=True, name="Calibri")
        c.alignment = Alignment(horizontal="center", vertical="center"); c.border = _border()

    ws.freeze_panes = "A6"; ws.sheet_view.showGridLines = False
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    fname = f"machine_loss_{plant.code}_{dt.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ════════════════════════════════════════════════════════
# MACHINE LOSS INPUTS – IMPORT
# ════════════════════════════════════════════════════════

@router.post("/machine-loss-inputs/import")
async def import_machine_loss_inputs(current_user: CurrentUser, plant: CurrentPlant, file: UploadFile = File(...)):
    """Import Machine Loss Inputs from Excel. Roles: administrator, plant_manager only."""
    _assert_role(current_user, IMPORT_ROLES, "Import Machine Loss")
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "File harus berformat .xlsx")
    contents = await file.read()
    try:
        wb = load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
    except:
        raise HTTPException(400, "File Excel tidak valid atau rusak")
    if "Import Template" not in wb.sheetnames:
        raise HTTPException(400, "Sheet 'Import Template' tidak ditemukan. Gunakan template yang disediakan.")

    ws = wb["Import Template"]
    db = _db(plant)
    lines  = {l.name.strip().lower(): l for l in db.query(MasterLine).filter(MasterLine.is_active == True).all()}
    shifts = {s.name.strip().lower(): s for s in db.query(MasterShift).filter(MasterShift.is_active == True).all()}
    fcodes = {f.code.strip().lower(): f for f in db.query(MasterFeedCode).filter(MasterFeedCode.is_active == True).all()}
    losses = {(ml.name.strip().lower(), ml.level): ml for ml in db.query(MachineLoss).filter(MachineLoss.is_active == True).all()}

    created, errors = 0, []
    for rn, row in enumerate(ws.iter_rows(min_row=4, values_only=True), start=4):
        if not any(row): continue
        cells = list(row) + [None]*11
        date_val,line_nm,shift_nm,fc_nm,l1_nm,l2_nm,l3_nm,tf,tt,dur_raw,remarks = cells[:11]
        errs = []
        try:
            parsed_date = dt.fromisoformat(str(date_val).strip()) if isinstance(date_val, str) else dt.combine(date_val, dt.min.time())
        except:
            errs.append("format date salah"); parsed_date = None
        lo = lines.get((line_nm or "").strip().lower())
        so = shifts.get((shift_nm or "").strip().lower())
        if not lo: errs.append(f"line '{line_nm}' tidak ditemukan")
        if not so: errs.append(f"shift '{shift_nm}' tidak ditemukan")
        fco = fcodes.get(str(fc_nm or "").strip().lower()) if fc_nm else None
        l1o = losses.get((str(l1_nm or "").strip().lower(), 1)) if l1_nm else None
        l2o = losses.get((str(l2_nm or "").strip().lower(), 2)) if l2_nm else None
        l3o = losses.get((str(l3_nm or "").strip().lower(), 3)) if l3_nm else None
        if fc_nm and not fco: errs.append(f"kode pakan '{fc_nm}' tidak ditemukan")
        if l1_nm and not l1o: errs.append(f"loss L1 '{l1_nm}' tidak ditemukan")
        if l2_nm and not l2o: errs.append(f"loss L2 '{l2_nm}' tidak ditemukan")
        if l3_nm and not l3o: errs.append(f"loss L3 '{l3_nm}' tidak ditemukan")
        try:
            dur = float(dur_raw or 0)
            if dur <= 0: raise ValueError()
        except:
            errs.append("duration_minutes harus angka > 0"); dur = None
        if errs: errors.append({"row": rn, "errors": errs}); continue
        db.add(MachineLossInput(date=parsed_date, line_id=lo.id, shift_id=so.id,
            feed_code_id=fco.id if fco else None,
            loss_l1_id=l1o.id if l1o else None, loss_l2_id=l2o.id if l2o else None,
            loss_l3_id=l3o.id if l3o else None,
            time_from=str(tf).strip() if tf else None, time_to=str(tt).strip() if tt else None,
            duration_minutes=dur, remarks=str(remarks).strip() if remarks else None,
            created_by_id=current_user.id))
        created += 1
    if created: db.commit()
    return {"imported": created, "errors": errors, "message": f"{created} baris berhasil diimport, {len(errors)} baris gagal."}
