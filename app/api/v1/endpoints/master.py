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
    MasterShift, MasterFeedCode, MasterLine, MasterStandardThroughput, StandardThroughputLog,
    MergedLine, MergedLineDetail,
    MasterOutputType, DEFAULT_OUTPUT_TYPES,
)
from app.schemas.master import (
    MachineLossLvl1Create, MachineLossLvl1Update, MachineLossLvl1Response,
    MachineLossLvl2Create, MachineLossLvl2Update, MachineLossLvl2Response,
    MachineLossLvl3Create, MachineLossLvl3Update, MachineLossLvl3Response,
    MasterMachineLossCreate, MasterMachineLossUpdate, MasterMachineLossResponse,
    ShiftCreate, ShiftUpdate, ShiftResponse,
    FeedCodeCreate, FeedCodeUpdate, FeedCodeResponse,
    LineCreate, LineUpdate, LineResponse,
    StandardThroughputCreate, StandardThroughputUpdate, StandardThroughputResponse, StandardThroughputLogResponse,
    MergedLineCreate, MergedLineUpdate, MergedLineResponse, MergedLineMemberResponse,
    OutputTypeCreate, OutputTypeUpdate, OutputTypeResponse,
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
        machine_losses_id=item.machine_losses_id,
        machine_losses_lvl_1_id=item.machine_losses_lvl_1_id,
        machine_losses_lvl_2_id=item.machine_losses_lvl_2_id,
        machine_losses_lvl_3_id=item.machine_losses_lvl_3_id,
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
    return db.query(MachineLossLvl1).order_by(MachineLossLvl1.machine_losses_lvl_1_id).all()


@router.post("/machine-loss-lvl1", response_model=MachineLossLvl1Response, status_code=201)
def create_lvl1(payload: MachineLossLvl1Create, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if db.query(MachineLossLvl1).filter(MachineLossLvl1.name == payload.name.strip()).first():
        raise HTTPException(400, f"Loss Level 1 '{payload.name}' sudah ada")
    item = MachineLossLvl1(name=payload.name.strip())
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/machine-loss-lvl1/{item_id}", response_model=MachineLossLvl1Response)
def update_lvl1(item_id: int, payload: MachineLossLvl1Update, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl1).filter(MachineLossLvl1.machine_losses_lvl_1_id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 1 not found")
    if payload.name:
        if db.query(MachineLossLvl1).filter(MachineLossLvl1.name == payload.name.strip(), MachineLossLvl1.machine_losses_lvl_1_id != item_id).first():
            raise HTTPException(400, f"Loss Level 1 '{payload.name}' sudah ada")
        item.name = payload.name.strip()
    db.commit(); db.refresh(item)
    return item


@router.delete("/machine-loss-lvl1/{item_id}", status_code=204)
def delete_lvl1(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl1).filter(MachineLossLvl1.machine_losses_lvl_1_id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 1 not found")
    if db.query(MasterMachineLoss).filter(MasterMachineLoss.machine_losses_lvl_1_id == item_id, MasterMachineLoss.is_active == True).first():
        raise HTTPException(400, "Loss Level 1 masih digunakan di Master Machine Losses")
    db.delete(item); db.commit()


# ════════════════════════════════════════════════════════
# MACHINE LOSS LEVEL 2
# ════════════════════════════════════════════════════════

@router.get("/machine-loss-lvl2", response_model=list[MachineLossLvl2Response])
def list_lvl2(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MachineLossLvl2).order_by(MachineLossLvl2.machine_losses_lvl_2_id).all()


@router.post("/machine-loss-lvl2", response_model=MachineLossLvl2Response, status_code=201)
def create_lvl2(payload: MachineLossLvl2Create, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if db.query(MachineLossLvl2).filter(MachineLossLvl2.name == payload.name.strip()).first():
        raise HTTPException(400, f"Loss Level 2 '{payload.name}' sudah ada")
    item = MachineLossLvl2(name=payload.name.strip())
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/machine-loss-lvl2/{item_id}", response_model=MachineLossLvl2Response)
def update_lvl2(item_id: int, payload: MachineLossLvl2Update, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl2).filter(MachineLossLvl2.machine_losses_lvl_2_id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 2 not found")
    if payload.name:
        if db.query(MachineLossLvl2).filter(MachineLossLvl2.name == payload.name.strip(), MachineLossLvl2.machine_losses_lvl_2_id != item_id).first():
            raise HTTPException(400, f"Loss Level 2 '{payload.name}' sudah ada")
        item.name = payload.name.strip()
    db.commit(); db.refresh(item)
    return item


@router.delete("/machine-loss-lvl2/{item_id}", status_code=204)
def delete_lvl2(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl2).filter(MachineLossLvl2.machine_losses_lvl_2_id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 2 not found")
    if db.query(MasterMachineLoss).filter(MasterMachineLoss.machine_losses_lvl_2_id == item_id, MasterMachineLoss.is_active == True).first():
        raise HTTPException(400, "Loss Level 2 masih digunakan di Master Machine Losses")
    db.delete(item); db.commit()


# ════════════════════════════════════════════════════════
# MACHINE LOSS LEVEL 3
# ════════════════════════════════════════════════════════

@router.get("/machine-loss-lvl3", response_model=list[MachineLossLvl3Response])
def list_lvl3(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    return db.query(MachineLossLvl3).order_by(MachineLossLvl3.machine_losses_lvl_3_id).all()


@router.post("/machine-loss-lvl3", response_model=MachineLossLvl3Response, status_code=201)
def create_lvl3(payload: MachineLossLvl3Create, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if db.query(MachineLossLvl3).filter(MachineLossLvl3.name == payload.name.strip()).first():
        raise HTTPException(400, f"Loss Level 3 '{payload.name}' sudah ada")
    item = MachineLossLvl3(name=payload.name.strip())
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/machine-loss-lvl3/{item_id}", response_model=MachineLossLvl3Response)
def update_lvl3(item_id: int, payload: MachineLossLvl3Update, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl3).filter(MachineLossLvl3.machine_losses_lvl_3_id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 3 not found")
    if payload.name:
        if db.query(MachineLossLvl3).filter(MachineLossLvl3.name == payload.name.strip(), MachineLossLvl3.machine_losses_lvl_3_id != item_id).first():
            raise HTTPException(400, f"Loss Level 3 '{payload.name}' sudah ada")
        item.name = payload.name.strip()
    db.commit(); db.refresh(item)
    return item


@router.delete("/machine-loss-lvl3/{item_id}", status_code=204)
def delete_lvl3(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MachineLossLvl3).filter(MachineLossLvl3.machine_losses_lvl_3_id == item_id).first()
    if not item: raise HTTPException(404, "Loss Level 3 not found")
    if db.query(MasterMachineLoss).filter(MasterMachineLoss.machine_losses_lvl_3_id == item_id, MasterMachineLoss.is_active == True).first():
        raise HTTPException(400, "Loss Level 3 masih digunakan di Master Machine Losses")
    db.delete(item); db.commit()


# ════════════════════════════════════════════════════════
# MASTER MACHINE LOSSES (katalog kombinasi)
# ════════════════════════════════════════════════════════

@router.get("/master-machine-losses", response_model=list[MasterMachineLossResponse])
def list_master_losses(current_user: CurrentUser, plant: CurrentPlant,
    machine_losses_lvl_1_id: int | None = None, machine_losses_lvl_2_id: int | None = None):
    db = _db(plant)
    q = db.query(MasterMachineLoss).filter(MasterMachineLoss.is_active == True)
    if machine_losses_lvl_1_id: q = q.filter(MasterMachineLoss.machine_losses_lvl_1_id == machine_losses_lvl_1_id)
    if machine_losses_lvl_2_id: q = q.filter(MasterMachineLoss.machine_losses_lvl_2_id == machine_losses_lvl_2_id)
    return [_build_master_loss_response(i) for i in q.order_by(MasterMachineLoss.machine_losses_lvl_1_id, MasterMachineLoss.machine_losses_lvl_2_id, MasterMachineLoss.machine_losses_lvl_3_id).all()]


@router.post("/master-machine-losses", response_model=MasterMachineLossResponse, status_code=201)
def create_master_loss(payload: MasterMachineLossCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    if not db.query(MachineLossLvl1).filter(MachineLossLvl1.machine_losses_lvl_1_id == payload.machine_losses_lvl_1_id).first():
        raise HTTPException(404, "Loss Level 1 tidak ditemukan")
    if payload.machine_losses_lvl_2_id:
        l2 = db.query(MachineLossLvl2).filter(MachineLossLvl2.machine_losses_lvl_2_id == payload.machine_losses_lvl_2_id).first()
        if not l2: raise HTTPException(404, "Loss Level 2 tidak ditemukan")
    if payload.machine_losses_lvl_3_id:
        l3 = db.query(MachineLossLvl3).filter(MachineLossLvl3.machine_losses_lvl_3_id == payload.machine_losses_lvl_3_id).first()
        if not l3: raise HTTPException(404, "Loss Level 3 tidak ditemukan")
    # Check duplicate combination
    dup_q = db.query(MasterMachineLoss).filter(MasterMachineLoss.machine_losses_lvl_1_id == payload.machine_losses_lvl_1_id, MasterMachineLoss.is_active == True)
    dup_q = dup_q.filter(MasterMachineLoss.machine_losses_lvl_2_id == payload.machine_losses_lvl_2_id)
    dup_q = dup_q.filter(MasterMachineLoss.machine_losses_lvl_3_id == payload.machine_losses_lvl_3_id)
    if dup_q.first(): raise HTTPException(400, "Kombinasi L1/L2/L3 ini sudah ada")
    item = MasterMachineLoss(machine_losses_lvl_1_id=payload.machine_losses_lvl_1_id, machine_losses_lvl_2_id=payload.machine_losses_lvl_2_id, machine_losses_lvl_3_id=payload.machine_losses_lvl_3_id, remarks=payload.remarks, created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return _build_master_loss_response(item)


@router.put("/master-machine-losses/{item_id}", response_model=MasterMachineLossResponse)
def update_master_loss(item_id: int, payload: MasterMachineLossUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterMachineLoss).filter(MasterMachineLoss.machine_losses_id == item_id, MasterMachineLoss.is_active == True).first()
    if not item: raise HTTPException(404, "Master Machine Loss tidak ditemukan")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return _build_master_loss_response(item)


@router.delete("/master-machine-losses/{item_id}", status_code=204)
def delete_master_loss(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterMachineLoss).filter(MasterMachineLoss.machine_losses_id == item_id).first()
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
    return db.query(MasterStandardThroughput).filter(MasterStandardThroughput.is_active == True).order_by(MasterStandardThroughput.id).all()


@router.post("/standard-throughputs", response_model=StandardThroughputResponse, status_code=201)
def create_standard_throughput(payload: StandardThroughputCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    dup = db.query(MasterStandardThroughput).filter(
        MasterStandardThroughput.line_id == payload.line_id,
        MasterStandardThroughput.feed_code_id == payload.feed_code_id,
        MasterStandardThroughput.is_active == True,
    ).first()
    if dup: raise HTTPException(400, "Kombinasi Line dan Kode Pakan ini sudah ada.")
    item = MasterStandardThroughput(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/standard-throughputs/{item_id}", response_model=StandardThroughputResponse)
def update_standard_throughput(item_id: int, payload: StandardThroughputUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterStandardThroughput).filter(MasterStandardThroughput.id == item_id, MasterStandardThroughput.is_active == True).first()
    if not item: raise HTTPException(404, "Standard throughput not found")
    new_line_id = payload.line_id if payload.line_id is not None else item.line_id
    new_feed_code_id = payload.feed_code_id if payload.feed_code_id is not None else item.feed_code_id
    dup = db.query(MasterStandardThroughput).filter(
        MasterStandardThroughput.line_id == new_line_id,
        MasterStandardThroughput.feed_code_id == new_feed_code_id,
        MasterStandardThroughput.is_active == True,
        MasterStandardThroughput.id != item_id,
    ).first()
    if dup: raise HTTPException(400, "Kombinasi Line dan Kode Pakan ini sudah ada.")
    count = db.query(StandardThroughputLog).filter(StandardThroughputLog.standard_throughput_id == item_id).count()
    log = StandardThroughputLog(
        standard_throughput_id=item_id,
        change_number=count + 1,
        old_throughput=item.standard_throughput,
        new_throughput=payload.standard_throughput if payload.standard_throughput is not None else item.standard_throughput,
        old_remarks=item.remarks,
        new_remarks=payload.remarks if payload.remarks is not None else item.remarks,
        reason=payload.reason,
        changed_by_id=current_user.id,
    )
    db.add(log)
    update_data = payload.model_dump(exclude_none=True)
    update_data.pop("reason", None)
    for k, v in update_data.items(): setattr(item, k, v)
    item.updated_by_id = current_user.id; db.commit(); db.refresh(item)
    return item


@router.get("/standard-throughputs/{item_id}/logs", response_model=list[StandardThroughputLogResponse])
def get_standard_throughput_logs(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterStandardThroughput).filter(MasterStandardThroughput.id == item_id).first()
    if not item: raise HTTPException(404, "Standard throughput not found")
    return db.query(StandardThroughputLog).filter(StandardThroughputLog.standard_throughput_id == item_id).order_by(StandardThroughputLog.id).all()


@router.delete("/standard-throughputs/{item_id}", status_code=204)
def delete_standard_throughput(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterStandardThroughput).filter(MasterStandardThroughput.id == item_id, MasterStandardThroughput.is_active == True).first()
    if not item: raise HTTPException(404, "Standard throughput not found")
    item.is_active = False; item.updated_by_id = current_user.id; db.commit()


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


# ════════════════════════════════════════════════════════
# OUTPUT TYPES (Master Output Type)
# ════════════════════════════════════════════════════════

def _seed_output_types(db) -> None:
    """Seed default output types if table is empty."""
    if db.query(MasterOutputType).count() == 0:
        for d in DEFAULT_OUTPUT_TYPES:
            db.add(MasterOutputType(**d))
        db.commit()


@router.get("/output-types", response_model=list[OutputTypeResponse])
def get_output_types(current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    _seed_output_types(db)
    return (
        db.query(MasterOutputType)
        .order_by(MasterOutputType.sort_order, MasterOutputType.id)
        .all()
    )


@router.get("/output-types/active", response_model=list[OutputTypeResponse])
def get_active_output_types(current_user: CurrentUser, plant: CurrentPlant):
    """Return only active output types — dipakai oleh form input."""
    db = _db(plant)
    _seed_output_types(db)
    return (
        db.query(MasterOutputType)
        .filter(MasterOutputType.is_active == True)
        .order_by(MasterOutputType.sort_order, MasterOutputType.id)
        .all()
    )


@router.post("/output-types", response_model=OutputTypeResponse, status_code=201)
def create_output_type(payload: OutputTypeCreate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    existing = db.query(MasterOutputType).filter(MasterOutputType.code == payload.code).first()
    if existing:
        raise HTTPException(400, f"Kode output type '{payload.code}' sudah digunakan")
    item = MasterOutputType(**payload.model_dump(), created_by_id=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.put("/output-types/{item_id}", response_model=OutputTypeResponse)
def update_output_type(item_id: int, payload: OutputTypeUpdate, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterOutputType).filter(MasterOutputType.id == item_id).first()
    if not item:
        raise HTTPException(404, "Output type tidak ditemukan")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    item.updated_by_id = current_user.id
    db.commit(); db.refresh(item)
    return item


@router.delete("/output-types/{item_id}", status_code=204)
def delete_output_type(item_id: int, current_user: CurrentUser, plant: CurrentPlant):
    db = _db(plant)
    item = db.query(MasterOutputType).filter(MasterOutputType.id == item_id).first()
    if not item:
        raise HTTPException(404, "Output type tidak ditemukan")
    item.is_active = False
    item.updated_by_id = current_user.id
    db.commit()
