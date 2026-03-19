"""
input.py
────────
Endpoint untuk input data transaksional OEE:
  - Production Output (produksi harian per shift per line)
  - (future: Machine Loss Input, Operating Time, dll)

URL prefix: /api/v1/input
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime as dt

from app.db.database import get_plant_db
from app.core.deps import CurrentUser, CurrentPlant
from app.models.plant_schema import (
    ProductionOutput,
    MachineLossInput, MachineLoss,
    MasterLine, MasterShift, MasterFeedCode,
)
from app.schemas.input import (
    ProductionOutputCreate, ProductionOutputUpdate, ProductionOutputResponse,
    MachineLossInputCreate, MachineLossInputUpdate, MachineLossInputResponse,
)

router = APIRouter(prefix="/input", tags=["Input Data"])


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _db(plant: CurrentPlant) -> Session:
    return next(get_plant_db(plant.schema_name))


def _build_output_response(item: ProductionOutput) -> dict:
    return {
        "id":              item.id,
        "date":            item.date,
        "line_id":         item.line_id,
        "shift_id":        item.shift_id,
        "feed_code_id":    item.feed_code_id,
        "production_plan": item.production_plan,
        "actual_output":   item.actual_output,
        "good_product":    item.good_product,
        "reject_product":  item.reject_product,
        "quality_rate":    item.quality_rate,
        "remarks":         item.remarks,
        "is_active":       item.is_active,
        "created_at":      item.created_at,
        "created_by_id":   item.created_by_id,
        "line_name":       item.line.name if item.line else None,
        "shift_name":      item.shift.name if item.shift else None,
        "feed_code_code":  item.feed_code.code if item.feed_code else None,
    }


def _compute_derived(actual_output: int, good_product: int) -> tuple[int, float]:
    """Hitung reject_product dan quality_rate dari actual dan good."""
    reject  = actual_output - good_product
    quality = round((good_product / actual_output * 100), 2) if actual_output > 0 else 0.0
    return reject, quality


# ════════════════════════════════════════════════════════
# PRODUCTION OUTPUTS
# ════════════════════════════════════════════════════════

@router.get("/production-outputs", response_model=list[ProductionOutputResponse])
def list_production_outputs(
    current_user: CurrentUser,
    plant: CurrentPlant,
    date_from: str | None = None,
    date_to:   str | None = None,
    line_id:   int | None = None,
    shift_id:  int | None = None,
):
    db = _db(plant)
    q = db.query(ProductionOutput).filter(ProductionOutput.is_active == True)
    if date_from:
        q = q.filter(ProductionOutput.date >= dt.fromisoformat(date_from))
    if date_to:
        q = q.filter(ProductionOutput.date <= dt.fromisoformat(date_to + "T23:59:59"))
    if line_id:
        q = q.filter(ProductionOutput.line_id == line_id)
    if shift_id:
        q = q.filter(ProductionOutput.shift_id == shift_id)

    items = q.order_by(ProductionOutput.date.desc(), ProductionOutput.id.desc()).all()
    return [_build_output_response(i) for i in items]


@router.post("/production-outputs", response_model=ProductionOutputResponse, status_code=201)
def create_production_output(
    payload: ProductionOutputCreate,
    current_user: CurrentUser,
    plant: CurrentPlant,
):
    db = _db(plant)

    line = db.query(MasterLine).filter(MasterLine.id == payload.line_id, MasterLine.is_active == True).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line tidak ditemukan")

    shift = db.query(MasterShift).filter(MasterShift.id == payload.shift_id, MasterShift.is_active == True).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift tidak ditemukan")

    if payload.feed_code_id:
        fc = db.query(MasterFeedCode).filter(
            MasterFeedCode.id == payload.feed_code_id, MasterFeedCode.is_active == True
        ).first()
        if not fc:
            raise HTTPException(status_code=404, detail="Kode pakan tidak ditemukan")

    reject, quality = _compute_derived(payload.actual_output, payload.good_product)

    item = ProductionOutput(
        date=payload.date,
        line_id=payload.line_id,
        shift_id=payload.shift_id,
        feed_code_id=payload.feed_code_id,
        production_plan=payload.production_plan,
        actual_output=payload.actual_output,
        good_product=payload.good_product,
        reject_product=reject,
        quality_rate=quality,
        remarks=payload.remarks,
        created_by_id=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _build_output_response(item)


@router.put("/production-outputs/{item_id}", response_model=ProductionOutputResponse)
def update_production_output(
    item_id: int,
    payload: ProductionOutputUpdate,
    current_user: CurrentUser,
    plant: CurrentPlant,
):
    db = _db(plant)
    item = db.query(ProductionOutput).filter(
        ProductionOutput.id == item_id, ProductionOutput.is_active == True
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Production output tidak ditemukan")

    data = payload.model_dump(exclude_none=True)

    if "line_id" in data:
        if not db.query(MasterLine).filter(MasterLine.id == data["line_id"], MasterLine.is_active == True).first():
            raise HTTPException(status_code=404, detail="Line tidak ditemukan")
    if "shift_id" in data:
        if not db.query(MasterShift).filter(MasterShift.id == data["shift_id"], MasterShift.is_active == True).first():
            raise HTTPException(status_code=404, detail="Shift tidak ditemukan")
    if "feed_code_id" in data and data["feed_code_id"]:
        if not db.query(MasterFeedCode).filter(
            MasterFeedCode.id == data["feed_code_id"], MasterFeedCode.is_active == True
        ).first():
            raise HTTPException(status_code=404, detail="Kode pakan tidak ditemukan")

    for k, v in data.items():
        setattr(item, k, v)

    reject, quality = _compute_derived(item.actual_output, item.good_product)
    item.reject_product = reject
    item.quality_rate   = quality
    item.updated_by_id  = current_user.id

    db.commit()
    db.refresh(item)
    return _build_output_response(item)


@router.delete("/production-outputs/{item_id}", status_code=204)
def delete_production_output(
    item_id: int,
    current_user: CurrentUser,
    plant: CurrentPlant,
):
    db = _db(plant)
    item = db.query(ProductionOutput).filter(ProductionOutput.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Production output tidak ditemukan")
    item.is_active     = False
    item.updated_by_id = current_user.id
    db.commit()


# ════════════════════════════════════════════════════════
# MACHINE LOSS INPUTS
# ════════════════════════════════════════════════════════

def _build_loss_response(item: MachineLossInput) -> dict:
    return {
        "id":               item.id,
        "date":             item.date,
        "line_id":          item.line_id,
        "shift_id":         item.shift_id,
        "feed_code_id":     item.feed_code_id,
        "loss_l1_id":       item.loss_l1_id,
        "loss_l2_id":       item.loss_l2_id,
        "loss_l3_id":       item.loss_l3_id,
        "time_from":        item.time_from,
        "time_to":          item.time_to,
        "duration_minutes": item.duration_minutes,
        "remarks":          item.remarks,
        "is_active":        item.is_active,
        "created_at":       item.created_at,
        "created_by_id":    item.created_by_id,
        "line_name":        item.line.name      if item.line      else None,
        "shift_name":       item.shift.name     if item.shift     else None,
        "feed_code_code":   item.feed_code.code if item.feed_code else None,
        "loss_l1_name":     item.loss_l1.name   if item.loss_l1   else None,
        "loss_l2_name":     item.loss_l2.name   if item.loss_l2   else None,
        "loss_l3_name":     item.loss_l3.name   if item.loss_l3   else None,
    }


def _validate_loss_refs(db, payload_dict: dict) -> None:
    """Validate all FK references that exist in the payload."""
    if payload_dict.get("line_id"):
        if not db.query(MasterLine).filter(MasterLine.id == payload_dict["line_id"], MasterLine.is_active == True).first():
            raise HTTPException(status_code=404, detail="Line not found")
    if payload_dict.get("shift_id"):
        if not db.query(MasterShift).filter(MasterShift.id == payload_dict["shift_id"], MasterShift.is_active == True).first():
            raise HTTPException(status_code=404, detail="Shift not found")
    if payload_dict.get("feed_code_id"):
        if not db.query(MasterFeedCode).filter(MasterFeedCode.id == payload_dict["feed_code_id"], MasterFeedCode.is_active == True).first():
            raise HTTPException(status_code=404, detail="Feed code not found")
    for field, level in [("loss_l1_id", 1), ("loss_l2_id", 2), ("loss_l3_id", 3)]:
        if payload_dict.get(field):
            node = db.query(MachineLoss).filter(
                MachineLoss.id == payload_dict[field],
                MachineLoss.level == level,
                MachineLoss.is_active == True,
            ).first()
            if not node:
                raise HTTPException(status_code=404, detail=f"Loss L{level} not found")


@router.get("/machine-loss-inputs", response_model=list[MachineLossInputResponse])
def list_machine_loss_inputs(
    current_user: CurrentUser,
    plant: CurrentPlant,
    date_from: str | None = None,
    date_to:   str | None = None,
    line_id:   int | None = None,
    shift_id:  int | None = None,
):
    db = _db(plant)
    q = db.query(MachineLossInput).filter(MachineLossInput.is_active == True)
    if date_from:
        q = q.filter(MachineLossInput.date >= dt.fromisoformat(date_from))
    if date_to:
        q = q.filter(MachineLossInput.date <= dt.fromisoformat(date_to + "T23:59:59"))
    if line_id:
        q = q.filter(MachineLossInput.line_id == line_id)
    if shift_id:
        q = q.filter(MachineLossInput.shift_id == shift_id)
    items = q.order_by(MachineLossInput.date.desc(), MachineLossInput.id.desc()).all()
    return [_build_loss_response(i) for i in items]


@router.post("/machine-loss-inputs", response_model=MachineLossInputResponse, status_code=201)
def create_machine_loss_input(
    payload: MachineLossInputCreate,
    current_user: CurrentUser,
    plant: CurrentPlant,
):
    db = _db(plant)
    _validate_loss_refs(db, payload.model_dump())

    item = MachineLossInput(
        date=payload.date,
        line_id=payload.line_id,
        shift_id=payload.shift_id,
        feed_code_id=payload.feed_code_id,
        loss_l1_id=payload.loss_l1_id,
        loss_l2_id=payload.loss_l2_id,
        loss_l3_id=payload.loss_l3_id,
        time_from=payload.time_from,
        time_to=payload.time_to,
        duration_minutes=payload.duration_minutes,
        remarks=payload.remarks,
        created_by_id=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _build_loss_response(item)


@router.put("/machine-loss-inputs/{item_id}", response_model=MachineLossInputResponse)
def update_machine_loss_input(
    item_id: int,
    payload: MachineLossInputUpdate,
    current_user: CurrentUser,
    plant: CurrentPlant,
):
    db = _db(plant)
    item = db.query(MachineLossInput).filter(
        MachineLossInput.id == item_id, MachineLossInput.is_active == True
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Machine loss input not found")

    data = payload.model_dump(exclude_none=True)
    _validate_loss_refs(db, data)

    for k, v in data.items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit()
    db.refresh(item)
    return _build_loss_response(item)


@router.delete("/machine-loss-inputs/{item_id}", status_code=204)
def delete_machine_loss_input(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossInput).filter(MachineLossInput.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Machine loss input not found")
    item.is_active     = False
    item.updated_by_id = current_user.id
    db.commit()
