"""
master.py
─────────
Machine Loss data flow:
  CREATE/UPDATE/DELETE → loss_level_1 / loss_level_2 / loss_level_3
  PostgreSQL trigger   → machine_losses auto-synced
  READ tree            → GET /machine-losses  (reads machine_losses)

machine_losses.source_id stores the original loss_level_X.id so we can
reliably look up the source record without guessing by name.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.database import get_plant_db
from app.core.deps import CurrentUser, CurrentPlant
from app.models.public import Plant
from app.models.plant_schema import (
    LossLevel1, LossLevel2, LossLevel3,
    MachineLoss,
    MasterShift, MasterFeedCode, MasterLine, MasterStandardThroughput,
)
from app.schemas.master import (
    LossLevel1Create, LossLevel1Update, LossLevel1Response,
    LossLevel2Create, LossLevel2Update, LossLevel2Response,
    LossLevel3Create, LossLevel3Update, LossLevel3Response,
    MachineLossResponse, MachineLossMoveRequest,
    ShiftCreate, ShiftUpdate, ShiftResponse,
    FeedCodeCreate, FeedCodeUpdate, FeedCodeResponse,
    LineCreate, LineUpdate, LineFeedCodeUpdate, LineResponse,
    StandardThroughputCreate, StandardThroughputUpdate, StandardThroughputResponse,
)

router = APIRouter(prefix="/master", tags=["Master Data"])


def _db(plant: Plant) -> Session:
    return next(get_plant_db(plant.schema_name))


def _get_ml(db: Session, ml_id: int) -> MachineLoss:
    ml = db.query(MachineLoss).filter(
        MachineLoss.id == ml_id, MachineLoss.is_active == True
    ).first()
    if not ml:
        raise HTTPException(status_code=404, detail=f"Node {ml_id} not found in machine_losses")
    return ml


def _ensure_source_id_column(db: Session, schema_name: str):
    """Add source_id column to machine_losses jika belum ada.

    Cek via information_schema dahulu — ALTER TABLE tidak dijalankan
    sama sekali kalau kolom sudah ada, sehingga tidak ada lock pada tabel.
    """
    try:
        result = db.execute(text("""
            SELECT 1 FROM information_schema.columns
             WHERE table_schema = :schema
               AND table_name   = 'machine_losses'
               AND column_name  = 'source_id'
        """), {"schema": schema_name}).first()
        if result is None:
            # Kolom belum ada — baru jalankan ALTER
            db.execute(text(f'ALTER TABLE "{schema_name}".machine_losses ADD COLUMN source_id INTEGER'))
            db.commit()
    except Exception:
        db.rollback()


# ─── Resolve source record from machine_losses ───────────────────────────────
def _get_source_l1(db: Session, ml: MachineLoss) -> LossLevel1 | None:
    """Get the loss_level_1 record that corresponds to this machine_losses node."""
    sid = getattr(ml, "source_id", None)
    if sid:
        return db.query(LossLevel1).filter(LossLevel1.id == sid).first()
    # Fallback: match by name (for rows without source_id)
    return db.query(LossLevel1).filter(
        LossLevel1.name == ml.name, LossLevel1.is_active == True
    ).first()


def _get_source_l2(db: Session, ml: MachineLoss) -> LossLevel2 | None:
    sid = getattr(ml, "source_id", None)
    if sid:
        return db.query(LossLevel2).filter(LossLevel2.id == sid).first()
    return db.query(LossLevel2).filter(
        LossLevel2.name == ml.name, LossLevel2.is_active == True
    ).first()


def _get_source_l3(db: Session, ml: MachineLoss) -> LossLevel3 | None:
    sid = getattr(ml, "source_id", None)
    if sid:
        return db.query(LossLevel3).filter(LossLevel3.id == sid).first()
    return db.query(LossLevel3).filter(
        LossLevel3.name == ml.name, LossLevel3.is_active == True
    ).first()


def _set_source_id(db: Session, ml: MachineLoss, source_id: int):
    """Persist source_id on the machine_losses row.

    Tidak pakai schema prefix eksplisit — koneksi sudah set search_path
    ke schema plant yang benar via get_plant_db().
    """
    try:
        db.execute(
            text("UPDATE machine_losses SET source_id = :sid WHERE id = :id"),
            {"sid": source_id, "id": ml.id}
        )
        db.flush()
    except Exception:
        pass  # column may not exist yet on very old DBs


# ════════════════════════════════════════════════════════
# LOSS LEVEL 1
# ════════════════════════════════════════════════════════

@router.get("/loss-level-1", response_model=list[LossLevel1Response])
def list_level1(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(LossLevel1).filter(LossLevel1.is_active == True).order_by(LossLevel1.sort_order, LossLevel1.id).all()


@router.post("/loss-level-1", response_model=LossLevel1Response, status_code=201)
def create_level1(payload: LossLevel1Create, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    count = db.query(LossLevel1).filter(LossLevel1.is_active == True).count()
    item = LossLevel1(
        name=payload.name, description=payload.description,
        sort_order=payload.sort_order or count,
        created_by_id=current_user.id,
    )
    db.add(item); db.commit(); db.refresh(item)
    # Backfill source_id on the machine_losses row created by trigger
    ml = db.query(MachineLoss).filter(
        MachineLoss.name == item.name, MachineLoss.level == 1, MachineLoss.is_active == True
    ).first()
    if ml:
        _set_source_id(db, ml, item.id)
        db.commit()
    db.refresh(item)  # refresh setelah semua commit agar tidak DetachedInstanceError
    return item


@router.put("/loss-level-1/{item_id}", response_model=LossLevel1Response)
def update_level1(item_id: int, payload: LossLevel1Update, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    # item_id may be loss_level_1.id or machine_losses.id
    item = db.query(LossLevel1).filter(LossLevel1.id == item_id).first()
    if not item:
        ml = db.query(MachineLoss).filter(MachineLoss.id == item_id, MachineLoss.level == 1).first()
        if ml:
            item = _get_source_l1(db, ml)
    if not item:
        raise HTTPException(status_code=404, detail="Loss Level 1 not found")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit(); db.refresh(item)
    return item


@router.delete("/loss-level-1/{item_id}", status_code=204)
def delete_level1(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(LossLevel1).filter(LossLevel1.id == item_id).first()
    if not item:
        ml = db.query(MachineLoss).filter(MachineLoss.id == item_id, MachineLoss.level == 1).first()
        if ml:
            item = _get_source_l1(db, ml)
    if not item:
        raise HTTPException(status_code=404, detail="Loss Level 1 not found")
    if db.query(LossLevel2).filter(LossLevel2.level_1_id == item.id, LossLevel2.is_active == True).first():
        raise HTTPException(status_code=400, detail="Remove Level 2 items first")
    item.is_active = False; item.updated_by_id = current_user.id
    db.commit()


# ════════════════════════════════════════════════════════
# LOSS LEVEL 2
# ════════════════════════════════════════════════════════

@router.get("/loss-level-2", response_model=list[LossLevel2Response])
def list_level2(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(LossLevel2).filter(LossLevel2.is_active == True).order_by(LossLevel2.level_1_id, LossLevel2.sort_order, LossLevel2.id).all()


@router.post("/loss-level-2", response_model=LossLevel2Response, status_code=201)
def create_level2(payload: LossLevel2Create, current_user: CurrentUser, plant: CurrentPlant):
    """
    level_1_id = machine_losses.id of the L1 parent.
    Backend resolves it to the real loss_level_1.id.
    """
    db = _db(plant)
    # Resolve: is it a machine_losses.id or a direct loss_level_1.id?
    real_l1_id: int | None = None

    ml_parent = db.query(MachineLoss).filter(
        MachineLoss.id == payload.level_1_id, MachineLoss.level == 1, MachineLoss.is_active == True
    ).first()
    if ml_parent:
        src = _get_source_l1(db, ml_parent)
        if src:
            real_l1_id = src.id

    if real_l1_id is None:
        direct = db.query(LossLevel1).filter(LossLevel1.id == payload.level_1_id, LossLevel1.is_active == True).first()
        if direct:
            real_l1_id = direct.id

    if real_l1_id is None:
        raise HTTPException(status_code=404, detail="Loss Level 1 parent not found")

    count = db.query(LossLevel2).filter(LossLevel2.level_1_id == real_l1_id, LossLevel2.is_active == True).count()
    item = LossLevel2(
        level_1_id=real_l1_id, name=payload.name,
        description=payload.description,
        sort_order=payload.sort_order or count,
        created_by_id=current_user.id,
    )
    db.add(item); db.commit(); db.refresh(item)
    # Backfill source_id
    ml = db.query(MachineLoss).filter(
        MachineLoss.name == item.name, MachineLoss.level == 2, MachineLoss.is_active == True
    ).first()
    if ml:
        _set_source_id(db, ml, item.id)
        db.commit()
    db.refresh(item)  # refresh setelah semua commit agar tidak DetachedInstanceError
    return item


@router.put("/loss-level-2/{item_id}", response_model=LossLevel2Response)
def update_level2(item_id: int, payload: LossLevel2Update, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(LossLevel2).filter(LossLevel2.id == item_id).first()
    if not item:
        ml = db.query(MachineLoss).filter(MachineLoss.id == item_id, MachineLoss.level == 2).first()
        if ml:
            item = _get_source_l2(db, ml)
    if not item:
        raise HTTPException(status_code=404, detail="Loss Level 2 not found")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit(); db.refresh(item)
    return item


@router.delete("/loss-level-2/{item_id}", status_code=204)
def delete_level2(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(LossLevel2).filter(LossLevel2.id == item_id).first()
    if not item:
        ml = db.query(MachineLoss).filter(MachineLoss.id == item_id, MachineLoss.level == 2).first()
        if ml:
            item = _get_source_l2(db, ml)
    if not item:
        raise HTTPException(status_code=404, detail="Loss Level 2 not found")
    if db.query(LossLevel3).filter(LossLevel3.level_2_id == item.id, LossLevel3.is_active == True).first():
        raise HTTPException(status_code=400, detail="Remove Level 3 items first")
    item.is_active = False; item.updated_by_id = current_user.id
    db.commit()


# ════════════════════════════════════════════════════════
# LOSS LEVEL 3
# ════════════════════════════════════════════════════════

@router.get("/loss-level-3", response_model=list[LossLevel3Response])
def list_level3(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(LossLevel3).filter(LossLevel3.is_active == True).order_by(LossLevel3.level_2_id, LossLevel3.sort_order, LossLevel3.id).all()


@router.post("/loss-level-3", response_model=LossLevel3Response, status_code=201)
def create_level3(payload: LossLevel3Create, current_user: CurrentUser, plant: CurrentPlant):
    """
    level_2_id = machine_losses.id of the L2 parent.
    Backend resolves it to the real loss_level_2.id.
    """
    db = _db(plant)
    real_l2_id: int | None = None

    ml_parent = db.query(MachineLoss).filter(
        MachineLoss.id == payload.level_2_id, MachineLoss.level == 2, MachineLoss.is_active == True
    ).first()
    if ml_parent:
        src = _get_source_l2(db, ml_parent)
        if src:
            real_l2_id = src.id

    if real_l2_id is None:
        direct = db.query(LossLevel2).filter(LossLevel2.id == payload.level_2_id, LossLevel2.is_active == True).first()
        if direct:
            real_l2_id = direct.id

    if real_l2_id is None:
        raise HTTPException(status_code=404, detail="Loss Level 2 parent not found")

    count = db.query(LossLevel3).filter(LossLevel3.level_2_id == real_l2_id, LossLevel3.is_active == True).count()
    item = LossLevel3(
        level_2_id=real_l2_id, name=payload.name,
        description=payload.description,
        sort_order=payload.sort_order or count,
        created_by_id=current_user.id,
    )
    db.add(item); db.commit(); db.refresh(item)
    # Backfill source_id
    ml = db.query(MachineLoss).filter(
        MachineLoss.name == item.name, MachineLoss.level == 3, MachineLoss.is_active == True
    ).first()
    if ml:
        _set_source_id(db, ml, item.id)
        db.commit()
    db.refresh(item)  # refresh setelah semua commit agar tidak DetachedInstanceError
    return item


@router.put("/loss-level-3/{item_id}", response_model=LossLevel3Response)
def update_level3(item_id: int, payload: LossLevel3Update, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(LossLevel3).filter(LossLevel3.id == item_id).first()
    if not item:
        ml = db.query(MachineLoss).filter(MachineLoss.id == item_id, MachineLoss.level == 3).first()
        if ml:
            item = _get_source_l3(db, ml)
    if not item:
        raise HTTPException(status_code=404, detail="Loss Level 3 not found")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit(); db.refresh(item)
    return item


@router.delete("/loss-level-3/{item_id}", status_code=204)
def delete_level3(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(LossLevel3).filter(LossLevel3.id == item_id).first()
    if not item:
        ml = db.query(MachineLoss).filter(MachineLoss.id == item_id, MachineLoss.level == 3).first()
        if ml:
            item = _get_source_l3(db, ml)
    if not item:
        raise HTTPException(status_code=404, detail="Loss Level 3 not found")
    item.is_active = False; item.updated_by_id = current_user.id
    db.commit()


# ════════════════════════════════════════════════════════
# MACHINE LOSSES  (read aggregation, handle cross-level drag)
# ════════════════════════════════════════════════════════

@router.get("/machine-losses", response_model=list[MachineLossResponse])
def list_machine_losses(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return (
        db.query(MachineLoss)
        .filter(MachineLoss.is_active == True)
        .order_by(MachineLoss.level, MachineLoss.sort_order, MachineLoss.id)
        .all()
    )


@router.patch("/machine-losses/{ml_id}/move", response_model=MachineLossResponse)
def move_machine_loss(
    ml_id: int,
    payload: MachineLossMoveRequest,
    current_user: CurrentUser,
    plant: CurrentPlant,
):
    """
    L3 reparent: move an L3 node to a different L2 parent.
    UPDATE loss_level_3.level_2_id → trigger updates machine_losses.parent_id.
    Juga update machine_losses langsung sebagai safety net.

    Fix: source_id di-backfill jika belum ada, fallback by source_id lebih diutamakan
    daripada by-name agar tidak salah ambil node dengan nama duplikat.
    """
    db = _db(plant)
    # _ensure_source_id_column tidak dipanggil di sini — sudah dihandle
    # saat startup via migrate_plant_schema. Memanggil ALTER TABLE tiap request
    # menyebabkan AccessExclusiveLock yang memblokir semua query lain.
    ml = _get_ml(db, ml_id)

    if ml.level != 3:
        raise HTTPException(status_code=400, detail="Only Level 3 nodes can be moved")

    if payload.new_parent_id is None:
        raise HTTPException(status_code=400, detail="Level 3 requires a parent (new_parent_id)")

    # ── Validate new parent is an active L2 ───────────────────────────────────
    new_parent_ml = db.query(MachineLoss).filter(
        MachineLoss.id == payload.new_parent_id,
        MachineLoss.is_active == True,
    ).first()
    if not new_parent_ml:
        raise HTTPException(status_code=404, detail=f"Parent node id={payload.new_parent_id} not found")
    if new_parent_ml.level != 2:
        raise HTTPException(status_code=400, detail="L3 can only be moved under an L2 parent")

    # ── Resolve loss_level_2 source record ────────────────────────────────────
    new_parent_l2 = _get_source_l2(db, new_parent_ml)
    if not new_parent_l2:
        # Last-resort: match by name among active L2 records
        new_parent_l2 = db.query(LossLevel2).filter(
            LossLevel2.name == new_parent_ml.name,
            LossLevel2.is_active == True,
        ).first()
    if not new_parent_l2:
        raise HTTPException(
            status_code=404,
            detail=f"loss_level_2 source not found for '{new_parent_ml.name}' (id={new_parent_ml.id}). "
                   "Run Sync dari Master terlebih dahulu."
        )
    # Ensure source_id is persisted on the parent for future calls
    if not getattr(new_parent_ml, "source_id", None):
        _set_source_id(db, new_parent_ml, new_parent_l2.id)

    # ── Resolve loss_level_3 source record ────────────────────────────────────
    l3_src = _get_source_l3(db, ml)
    if not l3_src:
        # Last-resort: match by name AND current parent to avoid wrong pick on duplicates
        current_parent_ml = db.query(MachineLoss).filter(
            MachineLoss.id == ml.parent_id,
            MachineLoss.is_active == True,
        ).first() if ml.parent_id else None

        current_l2_src = _get_source_l2(db, current_parent_ml) if current_parent_ml else None

        if current_l2_src:
            l3_src = db.query(LossLevel3).filter(
                LossLevel3.name == ml.name,
                LossLevel3.level_2_id == current_l2_src.id,
                LossLevel3.is_active == True,
            ).first()

        if not l3_src:
            # Broader fallback — by name only
            l3_src = db.query(LossLevel3).filter(
                LossLevel3.name == ml.name,
                LossLevel3.is_active == True,
            ).first()

    if not l3_src:
        raise HTTPException(
            status_code=404,
            detail=f"loss_level_3 source not found for '{ml.name}' (id={ml.id}). "
                   "Run Sync dari Master terlebih dahulu."
        )
    # Ensure source_id is persisted on the L3 machine_loss row
    if not getattr(ml, "source_id", None):
        _set_source_id(db, ml, l3_src.id)

    # ── Perform the move ──────────────────────────────────────────────────────
    # 1. Update loss_level_3 → trigger will sync machine_losses.parent_id
    l3_src.level_2_id    = new_parent_l2.id
    l3_src.sort_order    = payload.new_sort_order
    l3_src.updated_by_id = current_user.id
    db.flush()

    # 2. Update machine_losses directly as safety net (in case trigger is slow / missing)
    ml.parent_id     = payload.new_parent_id
    ml.sort_order    = payload.new_sort_order
    ml.updated_by_id = current_user.id
    db.commit()
    db.refresh(ml)
    return ml


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
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/shifts/{item_id}", response_model=ShiftResponse)
def update_shift(item_id: int, payload: ShiftUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterShift).filter(MasterShift.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="Shift not found")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/shifts/{item_id}", status_code=204)
def delete_shift(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterShift).filter(MasterShift.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="Shift not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


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
    if db.query(MasterFeedCode).filter(MasterFeedCode.code == payload.code, MasterFeedCode.is_active == True).first():
        raise HTTPException(status_code=400, detail="Feed code already exists")
    item = MasterFeedCode(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/feed-codes/{item_id}", response_model=FeedCodeResponse)
def update_feed_code(item_id: int, payload: FeedCodeUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterFeedCode).filter(MasterFeedCode.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="Feed code not found")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/feed-codes/{item_id}", status_code=204)
def delete_feed_code(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterFeedCode).filter(MasterFeedCode.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="Feed code not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


# ════════════════════════════════════════════════════════
# LINES
# ════════════════════════════════════════════════════════

@router.get("/lines", response_model=list[LineResponse])
def get_lines(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    lines = db.query(MasterLine).filter(MasterLine.is_active == True).order_by(MasterLine.id).all()
    # Attach current_feed_code_code ke setiap line untuk response
    result = []
    for line in lines:
        d = {
            "id": line.id,
            "plant_id": line.plant_id,
            "name": line.name,
            "code": line.code,
            "remarks": line.remarks,
            "current_feed_code_id": line.current_feed_code_id,
            "current_feed_code_code": line.current_feed_code.code if line.current_feed_code else None,
            "is_active": line.is_active,
            "created_at": line.created_at,
            "created_by_id": line.created_by_id,
        }
        result.append(d)
    return result


@router.post("/lines", response_model=LineResponse, status_code=201)
def create_line(payload: LineCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    # Validasi current_feed_code_id jika diisi
    if payload.current_feed_code_id:
        fc = db.query(MasterFeedCode).filter(MasterFeedCode.id == payload.current_feed_code_id, MasterFeedCode.is_active == True).first()
        if not fc:
            raise HTTPException(status_code=404, detail="Kode pakan tidak ditemukan")
    item = MasterLine(**payload.model_dump(), plant_id=plant.id, created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    # Load relasi
    if item.current_feed_code_id:
        db.refresh(item)
    return {
        "id": item.id, "plant_id": item.plant_id, "name": item.name,
        "code": item.code, "remarks": item.remarks,
        "current_feed_code_id": item.current_feed_code_id,
        "current_feed_code_code": item.current_feed_code.code if item.current_feed_code else None,
        "is_active": item.is_active, "created_at": item.created_at, "created_by_id": item.created_by_id,
    }


@router.put("/lines/{item_id}", response_model=LineResponse)
def update_line(item_id: int, payload: LineUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterLine).filter(MasterLine.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="Line not found")
    # Validasi current_feed_code_id jika diisi
    if payload.current_feed_code_id is not None:
        fc = db.query(MasterFeedCode).filter(MasterFeedCode.id == payload.current_feed_code_id, MasterFeedCode.is_active == True).first()
        if not fc:
            raise HTTPException(status_code=404, detail="Kode pakan tidak ditemukan")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return {
        "id": item.id, "plant_id": item.plant_id, "name": item.name,
        "code": item.code, "remarks": item.remarks,
        "current_feed_code_id": item.current_feed_code_id,
        "current_feed_code_code": item.current_feed_code.code if item.current_feed_code else None,
        "is_active": item.is_active, "created_at": item.created_at, "created_by_id": item.created_by_id,
    }

@router.patch("/lines/{item_id}/feed-code", response_model=LineResponse)
def set_line_feed_code(item_id: int, payload: LineFeedCodeUpdate, current_user: CurrentUser, plant: CurrentPlant):
    """Ganti atau hapus kode pakan aktif pada sebuah line."""
    db = _db(plant)
    item = db.query(MasterLine).filter(MasterLine.id == item_id, MasterLine.is_active == True).first()
    if not item: raise HTTPException(status_code=404, detail="Line tidak ditemukan")
    if payload.current_feed_code_id is not None:
        fc = db.query(MasterFeedCode).filter(MasterFeedCode.id == payload.current_feed_code_id, MasterFeedCode.is_active == True).first()
        if not fc:
            raise HTTPException(status_code=404, detail="Kode pakan tidak ditemukan")
    item.current_feed_code_id = payload.current_feed_code_id
    item.updated_by_id = current_user.id
    db.commit(); db.refresh(item)
    return {
        "id": item.id, "plant_id": item.plant_id, "name": item.name,
        "code": item.code, "remarks": item.remarks,
        "current_feed_code_id": item.current_feed_code_id,
        "current_feed_code_code": item.current_feed_code.code if item.current_feed_code else None,
        "is_active": item.is_active, "created_at": item.created_at, "created_by_id": item.created_by_id,
    }


@router.delete("/lines/{item_id}", status_code=204)
def delete_line(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterLine).filter(MasterLine.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="Line not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


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
    if db.query(MasterStandardThroughput).filter(
        MasterStandardThroughput.line_id == payload.line_id,
        MasterStandardThroughput.feed_code_id == payload.feed_code_id,
    ).first():
        raise HTTPException(status_code=400, detail="Line + feed code combination already exists")
    item = MasterStandardThroughput(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/standard-throughputs/{item_id}", response_model=StandardThroughputResponse)
def update_standard_throughput(item_id: int, payload: StandardThroughputUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterStandardThroughput).filter(MasterStandardThroughput.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="Standard throughput not found")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/standard-throughputs/{item_id}", status_code=204)
def delete_standard_throughput(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterStandardThroughput).filter(MasterStandardThroughput.id == item_id).first()
    if not item: raise HTTPException(status_code=404, detail="Standard throughput not found")
    db.delete(item); db.commit()