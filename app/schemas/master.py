from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, time


# ─── Master Machine Loss Level 1 ─────────────────────────────────────────────
class MachineLossLvl1Create(BaseModel):
    name: str
    description: Optional[str] = None
    sort_order: int = 0


class MachineLossLvl1Update(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class MachineLossLvl1Response(BaseModel):
    id: int
    name: str
    description: Optional[str]
    sort_order: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


# ─── Master Machine Loss Level 2 ─────────────────────────────────────────────
class MachineLossLvl2Create(BaseModel):
    lvl1_id: int
    name: str
    description: Optional[str] = None
    sort_order: int = 0


class MachineLossLvl2Update(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class MachineLossLvl2Response(BaseModel):
    id: int
    lvl1_id: int
    name: str
    description: Optional[str]
    sort_order: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


# ─── Master Machine Loss Level 3 ─────────────────────────────────────────────
class MachineLossLvl3Create(BaseModel):
    lvl2_id: int
    name: str
    description: Optional[str] = None
    sort_order: int = 0


class MachineLossLvl3Update(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class MachineLossLvl3Response(BaseModel):
    id: int
    lvl2_id: int
    name: str
    description: Optional[str]
    sort_order: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


# ─── Master Machine Losses (katalog kombinasi) ────────────────────────────────
class MasterMachineLossCreate(BaseModel):
    lvl1_id: int
    lvl2_id: Optional[int] = None
    lvl3_id: Optional[int] = None
    remarks: Optional[str] = None


class MasterMachineLossUpdate(BaseModel):
    lvl1_id: Optional[int] = None
    lvl2_id: Optional[int] = None
    lvl3_id: Optional[int] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class MasterMachineLossResponse(BaseModel):
    id: int
    lvl1_id: int
    lvl2_id: Optional[int]
    lvl3_id: Optional[int]
    remarks: Optional[str]
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    # Denormalized display names
    lvl1_name: Optional[str] = None
    lvl2_name: Optional[str] = None
    lvl3_name: Optional[str] = None
    model_config = {"from_attributes": True}


# ─── Shift ────────────────────────────────────────────────────────────────────
class ShiftBase(BaseModel):
    name: str
    time_from: time
    time_to: time
    remarks: Optional[str] = None


class ShiftCreate(ShiftBase):
    pass


class ShiftUpdate(BaseModel):
    name: Optional[str] = None
    time_from: Optional[time] = None
    time_to: Optional[time] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class ShiftResponse(ShiftBase):
    id: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


# ─── Feed Code ────────────────────────────────────────────────────────────────
class FeedCodeBase(BaseModel):
    code: str
    remarks: Optional[str] = None


class FeedCodeCreate(FeedCodeBase):
    pass


class FeedCodeUpdate(BaseModel):
    code: Optional[str] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class FeedCodeResponse(FeedCodeBase):
    id: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


# ─── Line ─────────────────────────────────────────────────────────────────────
class LineBase(BaseModel):
    name: str
    code: Optional[str] = None
    remarks: Optional[str] = None


class LineCreate(LineBase):
    pass


class LineUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class LineResponse(LineBase):
    id: int
    plant_id: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


# ─── Standard Throughput ──────────────────────────────────────────────────────
class StandardThroughputBase(BaseModel):
    line_id: int
    feed_code_id: int
    standard_throughput: int
    remarks: Optional[str] = None


class StandardThroughputCreate(StandardThroughputBase):
    pass


class StandardThroughputUpdate(BaseModel):
    standard_throughput: Optional[int] = None
    remarks: Optional[str] = None


class StandardThroughputResponse(StandardThroughputBase):
    id: int
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


# ─── Plant ────────────────────────────────────────────────────────────────────
class PlantCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


class PlantResponse(BaseModel):
    id: int
    name: str
    code: str
    schema_name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}

# ─── Merged Line ──────────────────────────────────────────────────────────────
class MergedLineCreate(BaseModel):
    name: str
    code: Optional[str] = None
    remarks: Optional[str] = None
    line_ids: list[int]  # minimal 2 line


class MergedLineUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    remarks: Optional[str] = None
    line_ids: Optional[list[int]] = None  # jika dikirim, replace seluruh detail
    is_active: Optional[bool] = None


class MergedLineMemberResponse(BaseModel):
    line_id: int
    line_name: str
    line_code: Optional[str] = None
    model_config = {"from_attributes": True}


class MergedLineResponse(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    remarks: Optional[str] = None
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int] = None
    members: list[MergedLineMemberResponse] = []
    model_config = {"from_attributes": True}
