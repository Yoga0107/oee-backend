"""
master.py
─────────
Machine Loss data flow (new 4-table ERD):
  master_machine_losses_lvl_1  — loss categories (L1)
  master_machine_losses_lvl_2  — sub-categories  (L2, FK → lvl1)
  master_machine_losses_lvl_3  — detail losses   (L3, FK → lvl2)
  master_machine_losses        — katalog kombinasi (FK → l1, l2, l3)
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_plant_db
from app.core.deps import CurrentUser, CurrentPlant
from app.models.public import Plant
from app.models.plant_schema import (
    MachineLossLvl1, MachineLossLvl2, MachineLossLvl3,
    MasterMachineLoss,
    MasterShift, MasterFeedCode, MasterLine, MasterStandardThroughput,
    MergedLine, MergedLineDetail,
)
from app.schemas.master import (
    MachineLossLvl1Create, MachineLossLvl1Update, MachineLossLvl1Response,
    MachineLossLvl2Create, MachineLossLvl2Update, MachineLossLvl2Response,
    MachineLossLvl3Create, MachineLossLvl3Update, MachineLossLvl3Response,
    MasterMachineLossCreate, MasterMachineLossUpdate, MasterMachineLossResponse,
    ShiftCreate, ShiftUpdate, ShiftResponse,
    FeedCodeCreate, FeedCodeUpdate, FeedCodeResponse,
    LineCreate, LineUpdate, LineResponse,
    StandardThroughputCreate, StandardThroughputUpdate, StandardThroughputResponse,
    MergedLineCreate, MergedLineUpdate, MergedLineResponse, MergedLineMemberResponse,
)

router = APIRouter(prefix="/master", tags=["Master Data"])


def _db(plant: Plant) -> Session:
    return next(get_plant_db(plant.schema_name))


def _shifts_overlap(from_a, to_a, from_b, to_b) -> bool:
    def to_minutes(ti) -> int:
        if hasattr(ti, 'hour'):
            return ti.hour * 60 + ti.minute
        h, m = str(ti).split(':')[:2]
        return int(h) * 60 + int(m)

    def normalize(start, end):
        s, e = to_minutes(start), to_minutes(end)
        if e <= s:
            return [(s, 1440), (0, e)]
        return [(s, e)]

    segs_a = normalize(from_a, to_a)
    segs_b = normalize(from_b, to_b)
    for (s1, e1) in segs_a:
        for (s2, e2) in segs_b:
            if s1 < e2 and s2 < e1:
                return True
    return False


def _build_master_loss_response(item: MasterMachineLoss) -> MasterMachineLossResponse:
    return MasterMachineLossResponse(
        id=item.id,
        lvl1_id=item.lvl1_id,
        lvl2_id=item.lvl2_id,
        lvl3_id=item.lvl3_id,
        remarks=item.remarks,
        is_active=item.is_active,
        created_at=item.created_at,
        created_by_id=item.created_by_id,
        lvl1_name=item.lvl1.name if item.lvl1 else None,
        lvl2_name=item.lvl2.name if item.lvl2 else None,
        lvl3_name=item.lvl3.name if item.lvl3 else None,
    )


# ════════════════════════════════════════════════════════
# MACHINE LOSS LEVEL 1
# ════════════════════════════════════════════════════════

@router.get("/machine-loss-lvl1", response_model=list[MachineLossLvl1Response])
def list_lvl1(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MachineLossLvl1).filter(MachineLossLvl1.is_active == True)\
        .order_by(MachineLossLvl1.sort_order, MachineLossLvl1.id).all()


@router.post("/machine-loss-lvl1", response_model=MachineLossLvl1Response, status_code=201)
def create_lvl1(payload: MachineLossLvl1Create, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if db.query(MachineLossLvl1).filter(MachineLossLvl1.name == payload.name.strip(), MachineLossLvl1.is_active == True).first():
        raise HTTPException(400, f"Loss Level 1 '{payload.name}' sudah ada")
    count = db.query(MachineLossLvl1).filter(MachineLossLvl1.is_active == True).count()
    item = MachineLossLvl1(name=payload.name.strip(), description=payload.description, sort_order=payload.sort_order or count, created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/machine-loss-lvl1/{item_id}", response_model=MachineLossLvl1Response)
def update_lvl1(item_id: int, payload: MachineLossLvl1Update, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl1).filter(MachineLossLvl1.id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 1 not found")
    if payload.name and payload.name.strip() != item.name:
        if db.query(MachineLossLvl1).filter(MachineLossLvl1.name == payload.name.strip(), MachineLossLvl1.is_active == True, MachineLossLvl1.id != item.id).first():
            raise HTTPException(400, f"Loss Level 1 '{payload.name}' sudah ada")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/machine-loss-lvl1/{item_id}", status_code=204)
def delete_lvl1(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl1).filter(MachineLossLvl1.id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 1 not found")
    if db.query(MachineLossLvl2).filter(MachineLossLvl2.lvl1_id == item.id, MachineLossLvl2.is_active == True).first():
        raise HTTPException(400, "Hapus semua Level 2 terlebih dahulu")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


# ════════════════════════════════════════════════════════
# MACHINE LOSS LEVEL 2
# ════════════════════════════════════════════════════════

@router.get("/machine-loss-lvl2", response_model=list[MachineLossLvl2Response])
def list_lvl2(current_user: CurrentUser, plant: CurrentPlant, lvl1_id: int | None = None):
    db = _db(plant)
    q = db.query(MachineLossLvl2).filter(MachineLossLvl2.is_active == True)
    if lvl1_id: q = q.filter(MachineLossLvl2.lvl1_id == lvl1_id)
    return q.order_by(MachineLossLvl2.lvl1_id, MachineLossLvl2.sort_order, MachineLossLvl2.id).all()


@router.post("/machine-loss-lvl2", response_model=MachineLossLvl2Response, status_code=201)
def create_lvl2(payload: MachineLossLvl2Create, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if not db.query(MachineLossLvl1).filter(MachineLossLvl1.id == payload.lvl1_id, MachineLossLvl1.is_active == True).first():
        raise HTTPException(404, "Loss Level 1 parent tidak ditemukan")
    if db.query(MachineLossLvl2).filter(MachineLossLvl2.lvl1_id == payload.lvl1_id, MachineLossLvl2.name == payload.name.strip(), MachineLossLvl2.is_active == True).first():
        raise HTTPException(400, f"Loss Level 2 '{payload.name}' sudah ada di parent ini")
    count = db.query(MachineLossLvl2).filter(MachineLossLvl2.lvl1_id == payload.lvl1_id, MachineLossLvl2.is_active == True).count()
    item = MachineLossLvl2(lvl1_id=payload.lvl1_id, name=payload.name.strip(), description=payload.description, sort_order=payload.sort_order or count, created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/machine-loss-lvl2/{item_id}", response_model=MachineLossLvl2Response)
def update_lvl2(item_id: int, payload: MachineLossLvl2Update, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl2).filter(MachineLossLvl2.id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 2 not found")
    if payload.name and payload.name.strip() != item.name:
        if db.query(MachineLossLvl2).filter(MachineLossLvl2.lvl1_id == item.lvl1_id, MachineLossLvl2.name == payload.name.strip(), MachineLossLvl2.is_active == True, MachineLossLvl2.id != item.id).first():
            raise HTTPException(400, f"Loss Level 2 '{payload.name}' sudah ada di parent ini")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/machine-loss-lvl2/{item_id}", status_code=204)
def delete_lvl2(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl2).filter(MachineLossLvl2.id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 2 not found")
    if db.query(MachineLossLvl3).filter(MachineLossLvl3.lvl2_id == item.id, MachineLossLvl3.is_active == True).first():
        raise HTTPException(400, "Hapus semua Level 3 terlebih dahulu")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


# ════════════════════════════════════════════════════════
# MACHINE LOSS LEVEL 3
# ════════════════════════════════════════════════════════

@router.get("/machine-loss-lvl3", response_model=list[MachineLossLvl3Response])
def list_lvl3(current_user: CurrentUser, plant: CurrentPlant, lvl2_id: int | None = None):
    db = _db(plant)
    q = db.query(MachineLossLvl3).filter(MachineLossLvl3.is_active == True)
    if lvl2_id: q = q.filter(MachineLossLvl3.lvl2_id == lvl2_id)
    return q.order_by(MachineLossLvl3.lvl2_id, MachineLossLvl3.sort_order, MachineLossLvl3.id).all()


@router.post("/machine-loss-lvl3", response_model=MachineLossLvl3Response, status_code=201)
def create_lvl3(payload: MachineLossLvl3Create, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if not db.query(MachineLossLvl2).filter(MachineLossLvl2.id == payload.lvl2_id, MachineLossLvl2.is_active == True).first():
        raise HTTPException(404, "Loss Level 2 parent tidak ditemukan")
    if db.query(MachineLossLvl3).filter(MachineLossLvl3.lvl2_id == payload.lvl2_id, MachineLossLvl3.name == payload.name.strip(), MachineLossLvl3.is_active == True).first():
        raise HTTPException(400, f"Loss Level 3 '{payload.name}' sudah ada di parent ini")
    count = db.query(MachineLossLvl3).filter(MachineLossLvl3.lvl2_id == payload.lvl2_id, MachineLossLvl3.is_active == True).count()
    item = MachineLossLvl3(lvl2_id=payload.lvl2_id, name=payload.name.strip(), description=payload.description, sort_order=payload.sort_order or count, created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/machine-loss-lvl3/{item_id}", response_model=MachineLossLvl3Response)
def update_lvl3(item_id: int, payload: MachineLossLvl3Update, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl3).filter(MachineLossLvl3.id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 3 not found")
    if payload.name and payload.name.strip() != item.name:
        if db.query(MachineLossLvl3).filter(MachineLossLvl3.lvl2_id == item.lvl2_id, MachineLossLvl3.name == payload.name.strip(), MachineLossLvl3.is_active == True, MachineLossLvl3.id != item.id).first():
            raise HTTPException(400, f"Loss Level 3 '{payload.name}' sudah ada di parent ini")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/machine-loss-lvl3/{item_id}", status_code=204)
def delete_lvl3(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl3).filter(MachineLossLvl3.id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 3 not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


# ════════════════════════════════════════════════════════
# MASTER MACHINE LOSSES (katalog kombinasi)
# ════════════════════════════════════════════════════════

@router.get("/master-machine-losses", response_model=list[MasterMachineLossResponse])
def list_master_losses(current_user: CurrentUser, plant: CurrentPlant,
    lvl1_id: int | None = None, lvl2_id: int | None = None):
    db = _db(plant)
    q = db.query(MasterMachineLoss).filter(MasterMachineLoss.is_active == True)
    if lvl1_id: q = q.filter(MasterMachineLoss.lvl1_id == lvl1_id)
    if lvl2_id: q = q.filter(MasterMachineLoss.lvl2_id == lvl2_id)
    return [_build_master_loss_response(i) for i in q.order_by(MasterMachineLoss.lvl1_id, MasterMachineLoss.lvl2_id, MasterMachineLoss.lvl3_id).all()]


@router.post("/master-machine-losses", response_model=MasterMachineLossResponse, status_code=201)
def create_master_loss(payload: MasterMachineLossCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if not db.query(MachineLossLvl1).filter(MachineLossLvl1.id == payload.lvl1_id, MachineLossLvl1.is_active == True).first():
        raise HTTPException(404, "Loss Level 1 tidak ditemukan")
    if payload.lvl2_id:
        l2 = db.query(MachineLossLvl2).filter(MachineLossLvl2.id == payload.lvl2_id, MachineLossLvl2.is_active == True).first()
        if not l2: raise HTTPException(404, "Loss Level 2 tidak ditemukan")
        if l2.lvl1_id != payload.lvl1_id: raise HTTPException(400, "Loss Level 2 tidak termasuk dalam Level 1 yang dipilih")
    if payload.lvl3_id:
        if not payload.lvl2_id: raise HTTPException(400, "Loss Level 2 harus dipilih sebelum Level 3")
        l3 = db.query(MachineLossLvl3).filter(MachineLossLvl3.id == payload.lvl3_id, MachineLossLvl3.is_active == True).first()
        if not l3: raise HTTPException(404, "Loss Level 3 tidak ditemukan")
        if l3.lvl2_id != payload.lvl2_id: raise HTTPException(400, "Loss Level 3 tidak termasuk dalam Level 2 yang dipilih")
    # Check duplicate combination
    dup_q = db.query(MasterMachineLoss).filter(MasterMachineLoss.lvl1_id == payload.lvl1_id, MasterMachineLoss.is_active == True)
    dup_q = dup_q.filter(MasterMachineLoss.lvl2_id == payload.lvl2_id)
    dup_q = dup_q.filter(MasterMachineLoss.lvl3_id == payload.lvl3_id)
    if dup_q.first(): raise HTTPException(400, "Kombinasi L1/L2/L3 ini sudah ada")
    item = MasterMachineLoss(lvl1_id=payload.lvl1_id, lvl2_id=payload.lvl2_id, lvl3_id=payload.lvl3_id, remarks=payload.remarks, created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return _build_master_loss_response(item)


@router.put("/master-machine-losses/{item_id}", response_model=MasterMachineLossResponse)
def update_master_loss(item_id: int, payload: MasterMachineLossUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterMachineLoss).filter(MasterMachineLoss.id == item_id, MasterMachineLoss.is_active == True).first()
    if not item: raise HTTPException(404, "Master Machine Loss tidak ditemukan")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return _build_master_loss_response(item)


@router.delete("/master-machine-losses/{item_id}", status_code=204)
def delete_master_loss(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterMachineLoss).filter(MasterMachineLoss.id == item_id).first()
    if not item: raise HTTPException(404, "Master Machine Loss tidak ditemukan")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


# ════════════════════════════════════════════════════════
# SHIFT
# ════════════════════════════════════════════════════════

@router.get("/shifts", response_model=list[ShiftResponse])
def get_shifts(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MasterShift).filter(MasterShift.is_active == True).order_by(MasterShift.id).all()


@router.post("/shifts", response_model=ShiftResponse, status_code=201)
def create_shift(payload: ShiftCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    existing = db.query(MasterShift).filter(MasterShift.is_active == True).all()
    for s in existing:
        if _shifts_overlap(s.time_from, s.time_to, payload.time_from, payload.time_to):
            raise HTTPException(400, f"Shift overlap dengan shift '{s.name}' ({s.time_from}–{s.time_to})")
    item = MasterShift(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/shifts/{item_id}", response_model=ShiftResponse)
def update_shift(item_id: int, payload: ShiftUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterShift).filter(MasterShift.id == item_id).first()
    if not item: raise HTTPException(404, "Shift not found")
    new_from = payload.time_from or item.time_from
    new_to   = payload.time_to   or item.time_to
    existing = db.query(MasterShift).filter(MasterShift.is_active == True, MasterShift.id != item_id).all()
    for s in existing:
        if _shifts_overlap(s.time_from, s.time_to, new_from, new_to):
            raise HTTPException(400, f"Shift overlap dengan shift '{s.name}' ({s.time_from}–{s.time_to})")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/shifts/{item_id}", status_code=204)
def delete_shift(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterShift).filter(MasterShift.id == item_id).first()
    if not item: raise HTTPException(404, "Shift not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


# ════════════════════════════════════════════════════════
# FEED CODE
# ════════════════════════════════════════════════════════

@router.get("/feed-codes", response_model=list[FeedCodeResponse])
def get_feed_codes(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MasterFeedCode).filter(MasterFeedCode.is_active == True).order_by(MasterFeedCode.id).all()


@router.post("/feed-codes", response_model=FeedCodeResponse, status_code=201)
def create_feed_code(payload: FeedCodeCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if db.query(MasterFeedCode).filter(MasterFeedCode.code == payload.code.strip(), MasterFeedCode.is_active == True).first():
        raise HTTPException(400, f"Kode pakan '{payload.code}' sudah ada")
    item = MasterFeedCode(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/feed-codes/{item_id}", response_model=FeedCodeResponse)
def update_feed_code(item_id: int, payload: FeedCodeUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterFeedCode).filter(MasterFeedCode.id == item_id).first()
    if not item: raise HTTPException(404, "Feed code not found")
    if payload.code and payload.code.strip() != item.code:
        if db.query(MasterFeedCode).filter(MasterFeedCode.code == payload.code.strip(), MasterFeedCode.is_active == True, MasterFeedCode.id != item_id).first():
            raise HTTPException(400, f"Kode pakan '{payload.code}' sudah ada")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/feed-codes/{item_id}", status_code=204)
def delete_feed_code(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterFeedCode).filter(MasterFeedCode.id == item_id).first()
    if not item: raise HTTPException(404, "Feed code not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


# ════════════════════════════════════════════════════════
# LINE
# ════════════════════════════════════════════════════════

@router.get("/lines", response_model=list[LineResponse])
def get_lines(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MasterLine).filter(MasterLine.is_active == True).order_by(MasterLine.id).all()


@router.post("/lines", response_model=LineResponse, status_code=201)
def create_line(payload: LineCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if db.query(MasterLine).filter(MasterLine.plant_id == plant.id, MasterLine.name == payload.name.strip(), MasterLine.is_active == True).first():
        raise HTTPException(400, f"Line '{payload.name}' sudah ada")
    item = MasterLine(plant_id=plant.id, name=payload.name.strip(), code=payload.code, remarks=payload.remarks, created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/lines/{item_id}", response_model=LineResponse)
def update_line(item_id: int, payload: LineUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterLine).filter(MasterLine.id == item_id).first()
    if not item: raise HTTPException(404, "Line not found")
    if payload.name and payload.name.strip() != item.name:
        if db.query(MasterLine).filter(MasterLine.plant_id == plant.id, MasterLine.name == payload.name.strip(), MasterLine.is_active == True, MasterLine.id != item_id).first():
            raise HTTPException(400, f"Line '{payload.name}' sudah ada")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/lines/{item_id}", status_code=204)
def delete_line(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterLine).filter(MasterLine.id == item_id).first()
    if not item: raise HTTPException(404, "Line not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


# ════════════════════════════════════════════════════════
# STANDARD THROUGHPUT
# ════════════════════════════════════════════════════════

@router.get("/standard-throughputs", response_model=list[StandardThroughputResponse])
def get_standard_throughputs(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MasterStandardThroughput).order_by(MasterStandardThroughput.id).all()


@router.post("/standard-throughputs", response_model=StandardThroughputResponse, status_code=201)
def create_standard_throughput(payload: StandardThroughputCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = MasterStandardThroughput(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/standard-throughputs/{item_id}", response_model=StandardThroughputResponse)
def update_standard_throughput(item_id: int, payload: StandardThroughputUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterStandardThroughput).filter(MasterStandardThroughput.id == item_id).first()
    if not item: raise HTTPException(404, "Standard throughput not found")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.delete("/standard-throughputs/{item_id}", status_code=204)
def delete_standard_throughput(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterStandardThroughput).filter(MasterStandardThroughput.id == item_id).first()
    if not item: raise HTTPException(404, "Standard throughput not found")
    db.delete(item); db.commit()


# ════════════════════════════════════════════════════════
# MERGED LINES
# ════════════════════════════════════════════════════════

def _build_merged_response(ml: MergedLine) -> dict:
    return {
        "id": ml.id, "name": ml.name, "code": ml.code, "remarks": ml.remarks,
        "is_active": ml.is_active, "created_at": ml.created_at, "created_by_id": ml.created_by_id,
        "members": [{"line_id": d.line_id, "line_name": d.line.name, "line_code": d.line.code} for d in ml.details],
    }


@router.get("/merged-lines", response_model=list[MergedLineResponse])
def get_merged_lines(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return [_build_merged_response(i) for i in db.query(MergedLine).filter(MergedLine.is_active == True).order_by(MergedLine.id).all()]


@router.get("/merged-lines/{item_id}", response_model=MergedLineResponse)
def get_merged_line(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MergedLine).filter(MergedLine.id == item_id).first()
    if not item: raise HTTPException(404, "Merged line not found")
    return _build_merged_response(item)


@router.post("/merged-lines", response_model=MergedLineResponse, status_code=201)
def create_merged_line(payload: MergedLineCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if len(payload.line_ids) < 2: raise HTTPException(400, "Minimal 2 line harus dipilih")
    item = MergedLine(name=payload.name, code=payload.code, remarks=payload.remarks, created_by_id=current_user.id)
    db.add(item); db.flush()
    for lid in payload.line_ids:
        line = db.query(MasterLine).filter(MasterLine.id == lid).first()
        if not line: db.rollback(); raise HTTPException(404, f"Line {lid} tidak ditemukan")
        db.add(MergedLineDetail(merged_line_id=item.id, line_id=lid))
    db.commit(); db.refresh(item)
    return _build_merged_response(item)


@router.put("/merged-lines/{item_id}", response_model=MergedLineResponse)
def update_merged_line(item_id: int, payload: MergedLineUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MergedLine).filter(MergedLine.id == item_id).first()
    if not item: raise HTTPException(404, "Merged line not found")
    if payload.name is not None: item.name = payload.name
    if payload.code is not None: item.code = payload.code
    if payload.remarks is not None: item.remarks = payload.remarks
    if payload.is_active is not None: item.is_active = payload.is_active
    if payload.line_ids is not None:
        if len(payload.line_ids) < 2: raise HTTPException(400, "Minimal 2 line harus dipilih")
        for d in item.details: db.delete(d)
        db.flush()
        for lid in payload.line_ids:
            line = db.query(MasterLine).filter(MasterLine.id == lid).first()
            if not line: db.rollback(); raise HTTPException(404, f"Line {lid} tidak ditemukan")
            db.add(MergedLineDetail(merged_line_id=item.id, line_id=lid))
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return _build_merged_response(item)


@router.delete("/merged-lines/{item_id}", status_code=204)
def delete_merged_line(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MergedLine).filter(MergedLine.id == item_id).first()
    if not item: raise HTTPException(404, "Merged line not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()
