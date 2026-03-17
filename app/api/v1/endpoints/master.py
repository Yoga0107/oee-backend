from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_plant_db
from app.core.deps import CurrentUser, CurrentPlant
from app.models.public import Plant
from app.models.plant_schema import (
    MachineLoss,
    MasterShift, MasterFeedCode, MasterLine, MasterStandardThroughput,
)
from app.schemas.master import (
    MachineLossCreate, MachineLossUpdate, MachineLossResponse, MachineLossMoveRequest,
    ShiftCreate, ShiftUpdate, ShiftResponse,
    FeedCodeCreate, FeedCodeUpdate, FeedCodeResponse,
    LineCreate, LineUpdate, LineResponse,
    StandardThroughputCreate, StandardThroughputUpdate, StandardThroughputResponse,
)

router = APIRouter(prefix="/master", tags=["Master Data"])


def _db(plant: Plant) -> Session:
    return next(get_plant_db(plant.schema_name))


# ════════════════════════════════════════════════════════
# MACHINE LOSS  (unified self-referencing)
# ════════════════════════════════════════════════════════

@router.get("/machine-losses", response_model=list[MachineLossResponse])
def list_machine_losses(current_user: CurrentUser, plant: CurrentPlant):
    """Return all ACTIVE machine loss nodes (flat list, sorted by sort_order)."""
    db = _db(plant)
    return (
        db.query(MachineLoss)
        .filter(MachineLoss.is_active == True)
        .order_by(MachineLoss.level, MachineLoss.sort_order, MachineLoss.id)
        .all()
    )


@router.post("/machine-losses", response_model=MachineLossResponse, status_code=201)
def create_machine_loss(payload: MachineLossCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    # Validate parent exists and level is consistent
    if payload.parent_id:
        parent = db.query(MachineLoss).filter(
            MachineLoss.id == payload.parent_id,
            MachineLoss.is_active == True,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent tidak ditemukan")
        if payload.level != parent.level + 1:
            raise HTTPException(status_code=400, detail=f"Level harus {parent.level + 1} untuk parent ini")
    else:
        if payload.level != 1:
            raise HTTPException(status_code=400, detail="Node tanpa parent harus level 1")

    item = MachineLoss(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/machine-losses/{item_id}", response_model=MachineLossResponse)
def update_machine_loss(
    item_id: int, payload: MachineLossUpdate,
    current_user: CurrentUser, plant: CurrentPlant,
):
    db = _db(plant)
    item = db.query(MachineLoss).filter(MachineLoss.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Machine loss tidak ditemukan")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit()
    db.refresh(item)
    return item


@router.patch("/machine-losses/{item_id}/move", response_model=MachineLossResponse)
def move_machine_loss(
    item_id: int, payload: MachineLossMoveRequest,
    current_user: CurrentUser, plant: CurrentPlant,
):
    """
    Drag & drop endpoint.
    Move a node to a new parent without changing its ID.
    Also updates level and sort_order.
    """
    db = _db(plant)
    item = db.query(MachineLoss).filter(MachineLoss.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Machine loss tidak ditemukan")

    # Guard: cannot move into own subtree
    if payload.new_parent_id:
        parent = db.query(MachineLoss).filter(MachineLoss.id == payload.new_parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent baru tidak ditemukan")
        if payload.new_level != parent.level + 1:
            raise HTTPException(status_code=400, detail="Level tidak konsisten dengan parent baru")
        # Check not moving into own descendant
        ancestor_id = parent.parent_id
        while ancestor_id:
            if ancestor_id == item_id:
                raise HTTPException(status_code=400, detail="Tidak bisa memindah node ke dalam subtree-nya sendiri")
            anc = db.query(MachineLoss).filter(MachineLoss.id == ancestor_id).first()
            ancestor_id = anc.parent_id if anc else None
    else:
        if payload.new_level != 1:
            raise HTTPException(status_code=400, detail="Node tanpa parent harus level 1")

    item.parent_id   = payload.new_parent_id
    item.level       = payload.new_level
    item.sort_order  = payload.new_sort_order
    item.updated_by_id = current_user.id
    db.commit()
    db.refresh(item)
    return item


@router.delete("/machine-losses/{item_id}", status_code=204)
def delete_machine_loss(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    """Soft delete — set is_active = False. Also soft-deletes all descendants."""
    db = _db(plant)
    item = db.query(MachineLoss).filter(MachineLoss.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Machine loss tidak ditemukan")

    # Recursively soft-delete all descendants
    def soft_delete_tree(node_id: int):
        children = db.query(MachineLoss).filter(
            MachineLoss.parent_id == node_id,
            MachineLoss.is_active == True,
        ).all()
        for child in children:
            soft_delete_tree(child.id)
            child.is_active = False
            child.updated_by_id = current_user.id

    soft_delete_tree(item_id)
    item.is_active = False
    item.updated_by_id = current_user.id
    db.commit()


# ════════════════════════════════════════════════════════
# SHIFTS
# ════════════════════════════════════════════════════════

@router.get("/shifts", response_model=list[ShiftResponse])
def get_shifts(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MasterShift).filter(MasterShift.is_active == True).order_by(MasterShift.id).all()


@router.post("/shifts", response_model=ShiftResponse, status_code=201)
def create_shift(payload: ShiftCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = MasterShift(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/shifts/{item_id}", response_model=ShiftResponse)
def update_shift(item_id: int, payload: ShiftUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterShift).filter(MasterShift.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Shift tidak ditemukan")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit()
    db.refresh(item)
    return item


@router.delete("/shifts/{item_id}", status_code=204)
def delete_shift(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    """Soft delete."""
    db = _db(plant)
    item = db.query(MasterShift).filter(MasterShift.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Shift tidak ditemukan")
    item.is_active = False
    item.updated_by_id = current_user.id
    db.commit()


# ════════════════════════════════════════════════════════
# FEED CODES
# ════════════════════════════════════════════════════════

@router.get("/feed-codes", response_model=list[FeedCodeResponse])
def get_feed_codes(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MasterFeedCode).filter(MasterFeedCode.is_active == True).order_by(MasterFeedCode.id).all()


@router.post("/feed-codes", response_model=FeedCodeResponse, status_code=201)
def create_feed_code(payload: FeedCodeCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    existing = db.query(MasterFeedCode).filter(
        MasterFeedCode.code == payload.code, MasterFeedCode.is_active == True
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Feed code sudah ada")
    item = MasterFeedCode(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/feed-codes/{item_id}", response_model=FeedCodeResponse)
def update_feed_code(item_id: int, payload: FeedCodeUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterFeedCode).filter(MasterFeedCode.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Feed code tidak ditemukan")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit()
    db.refresh(item)
    return item


@router.delete("/feed-codes/{item_id}", status_code=204)
def delete_feed_code(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    """Soft delete."""
    db = _db(plant)
    item = db.query(MasterFeedCode).filter(MasterFeedCode.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Feed code tidak ditemukan")
    item.is_active = False
    item.updated_by_id = current_user.id
    db.commit()


# ════════════════════════════════════════════════════════
# LINES
# ════════════════════════════════════════════════════════

@router.get("/lines", response_model=list[LineResponse])
def get_lines(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MasterLine).filter(MasterLine.is_active == True).order_by(MasterLine.id).all()


@router.post("/lines", response_model=LineResponse, status_code=201)
def create_line(payload: LineCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = MasterLine(**payload.model_dump(), plant_id=plant.id, created_by_id=current_user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/lines/{item_id}", response_model=LineResponse)
def update_line(item_id: int, payload: LineUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterLine).filter(MasterLine.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Line tidak ditemukan")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit()
    db.refresh(item)
    return item


@router.delete("/lines/{item_id}", status_code=204)
def delete_line(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    """Soft delete."""
    db = _db(plant)
    item = db.query(MasterLine).filter(MasterLine.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Line tidak ditemukan")
    item.is_active = False
    item.updated_by_id = current_user.id
    db.commit()


# ════════════════════════════════════════════════════════
# STANDARD THROUGHPUTS
# ════════════════════════════════════════════════════════

@router.get("/standard-throughputs", response_model=list[StandardThroughputResponse])
def get_standard_throughputs(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MasterStandardThroughput).order_by(MasterStandardThroughput.id).all()


@router.post("/standard-throughputs", response_model=StandardThroughputResponse, status_code=201)
def create_standard_throughput(payload: StandardThroughputCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    existing = db.query(MasterStandardThroughput).filter(
        MasterStandardThroughput.line_id == payload.line_id,
        MasterStandardThroughput.feed_code_id == payload.feed_code_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Kombinasi line + feed code sudah ada")
    item = MasterStandardThroughput(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/standard-throughputs/{item_id}", response_model=StandardThroughputResponse)
def update_standard_throughput(
    item_id: int, payload: StandardThroughputUpdate,
    current_user: CurrentUser, plant: CurrentPlant,
):
    db = _db(plant)
    item = db.query(MasterStandardThroughput).filter(MasterStandardThroughput.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Standard throughput tidak ditemukan")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit()
    db.refresh(item)
    return item


@router.delete("/standard-throughputs/{item_id}", status_code=204)
def delete_standard_throughput(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    """Hard delete — throughput tidak punya soft delete."""
    db = _db(plant)
    item = db.query(MasterStandardThroughput).filter(MasterStandardThroughput.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Standard throughput tidak ditemukan")
    db.delete(item)
    db.commit()
