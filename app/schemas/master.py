from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, time


# ─── Machine Loss (Index Transacition) ────────────────
class MachineLossCreate(BaseModel):
    parent_id: Optional[int] = None
    level: int
    name: str
    description: Optional[str] = None
    sort_order: int = 0

    @field_validator("level")
    @classmethod
    def level_valid(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError("level harus 1, 2, atau 3")
        return v


class MachineLossUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class MachineLossResponse(BaseModel):
    id: int
    parent_id: Optional[int]
    level: int
    name: str
    description: Optional[str]
    sort_order: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


class MachineLossMoveRequest(BaseModel):
    """Payload drag & drop — pindah node ke parent baru."""
    new_parent_id: Optional[int]
    new_level: int
    new_sort_order: int


# ─── Loss Level 1 ────────────────────────────────────────────────────────────
class LossLevel1Create(BaseModel):
    name: str
    description: Optional[str] = None
    sort_order: int = 0


class LossLevel1Update(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class LossLevel1Response(BaseModel):
    id: int
    name: str
    description: Optional[str]
    sort_order: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


# ─── Loss Level 2 ────────────────────────────────────────────────────────────
class LossLevel2Create(BaseModel):
    level_1_id: int
    name: str
    description: Optional[str] = None
    sort_order: int = 0


class LossLevel2Update(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class LossLevel2Response(BaseModel):
    id: int
    level_1_id: int
    name: str
    description: Optional[str]
    sort_order: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
    model_config = {"from_attributes": True}


# ─── Loss Level 3 ────────────────────────────────────────────────────────────
class LossLevel3Create(BaseModel):
    level_2_id: int
    name: str
    description: Optional[str] = None
    sort_order: int = 0


class LossLevel3Update(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class LossLevel3Response(BaseModel):
    id: int
    level_2_id: int
    name: str
    description: Optional[str]
    sort_order: int
    is_active: bool
    created_at: datetime
    created_by_id: Optional[int]
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
