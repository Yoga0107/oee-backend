from pydantic import BaseModel, field_validator
from typing import Optional, Literal
from datetime import datetime, time


# ─── Master Machine Loss Level 1 ─────────────────────────────────────────────
class MachineLossLvl1Create(BaseModel):
    name: str


class MachineLossLvl1Update(BaseModel):
    name: Optional[str] = None


class MachineLossLvl1Response(BaseModel):
    machine_losses_lvl_1_id: int
    name: str
    model_config = {"from_attributes": True}


# ─── Master Machine Loss Level 2 ─────────────────────────────────────────────
class MachineLossLvl2Create(BaseModel):
    name: str


class MachineLossLvl2Update(BaseModel):
    name: Optional[str] = None


class MachineLossLvl2Response(BaseModel):
    machine_losses_lvl_2_id: int
    name: str
    model_config = {"from_attributes": True}


# ─── Master Machine Loss Level 3 ─────────────────────────────────────────────
class MachineLossLvl3Create(BaseModel):
    name: str


class MachineLossLvl3Update(BaseModel):
    name: Optional[str] = None


class MachineLossLvl3Response(BaseModel):
    machine_losses_lvl_3_id: int
    name: str
    model_config = {"from_attributes": True}


# ─── Master Machine Losses (katalog kombinasi) ────────────────────────────────
class MasterMachineLossCreate(BaseModel):
    machine_losses_lvl_1_id: int
    machine_losses_lvl_2_id: Optional[int] = None
    machine_losses_lvl_3_id: Optional[int] = None
    remarks: Optional[str] = None


class MasterMachineLossUpdate(BaseModel):
    machine_losses_lvl_1_id: Optional[int] = None
    machine_losses_lvl_2_id: Optional[int] = None
    machine_losses_lvl_3_id: Optional[int] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class MasterMachineLossResponse(BaseModel):
    machine_losses_id: int
    machine_losses_lvl_1_id: int
    machine_losses_lvl_2_id: Optional[int]
    machine_losses_lvl_3_id: Optional[int]
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
# MODIFIKASI: LineCreate sekarang tidak lagi digunakan untuk membuat merged line.
# Untuk line fisik, gunakan LineCreate (type default = 'physical').
# Untuk merged line, gunakan MergedLineCreate yang akan otomatis set type = 'merged'.
class LineBase(BaseModel):
    name: str
    code: Optional[str] = None
    remarks: Optional[str] = None


class LineCreate(LineBase):
    pass  # type selalu 'physical', diset di endpoint


class LineUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class LineResponse(LineBase):
    id: int
    plant_id: int
    type: str  # 'physical' | 'merged'
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
    line_id: Optional[int] = None
    feed_code_id: Optional[int] = None
    standard_throughput: Optional[int] = None
    remarks: Optional[str] = None
    reason: Optional[str] = None


class StandardThroughputLogResponse(BaseModel):
    id: int
    standard_throughput_id: int
    change_number: int
    old_throughput: Optional[int]
    new_throughput: int
    old_remarks: Optional[str]
    new_remarks: Optional[str]
    reason: Optional[str]
    changed_at: datetime
    changed_by_id: Optional[int]
    model_config = {"from_attributes": True}


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


# ─── Merged Line (via IntLineMerge) ──────────────────────────────────────────
# MODIFIKASI: MergedLine tidak lagi tabel terpisah.
# Merged line = MasterLine dengan type='merged' + relasi di int_line_merge.
# child_line_ids boleh berisi ID dari line fisik (type='physical') MAUPUN
# line hasil merge (type='merged') → mendukung penggabungan bertingkat.
#
# Contoh:
#   LineA (physical) + LineB (physical) → LINE_AB (merged)
#   LineC (physical) + LineD (physical) → LINE_CD (merged)
#   LINE_AB (merged) + LINE_CD (merged) → LINE_ABCD (merged)  ← bertingkat!

class MergedLineCreate(BaseModel):
    name: str
    code: Optional[str] = None
    remarks: Optional[str] = None
    child_line_ids: list[int]  # minimal 2; boleh mix physical & merged line

    @field_validator("child_line_ids")
    @classmethod
    def validate_min_children(cls, v: list[int]) -> list[int]:
        if len(v) < 2:
            raise ValueError("Minimal 2 line harus dipilih")
        if len(v) != len(set(v)):
            raise ValueError("child_line_ids tidak boleh duplikat")
        return v


class MergedLineUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    remarks: Optional[str] = None
    child_line_ids: Optional[list[int]] = None  # jika dikirim, replace seluruh relasi
    is_active: Optional[bool] = None

    @field_validator("child_line_ids")
    @classmethod
    def validate_min_children(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is not None:
            if len(v) < 2:
                raise ValueError("Minimal 2 line harus dipilih")
            if len(v) != len(set(v)):
                raise ValueError("child_line_ids tidak boleh duplikat")
        return v


class MergedChildResponse(BaseModel):
    """Representasi satu child line di dalam merged line."""
    line_id:   int
    line_name: str
    line_code: Optional[str] = None
    line_type: str  # 'physical' | 'merged' — membantu FE menampilkan hierarki
    model_config = {"from_attributes": True}


class MergedLineResponse(BaseModel):
    """
    Response untuk merged line (MasterLine dengan type='merged').
    Field `children` berisi daftar langsung child-nya saja (bukan rekursif),
    sehingga FE bisa membangun pohon secara mandiri.
    """
    id:             int
    name:           str
    code:           Optional[str] = None
    remarks:        Optional[str] = None
    type:           str  # selalu 'merged'
    is_active:      bool
    created_at:     datetime
    created_by_id:  Optional[int] = None
    updated_at:     Optional[datetime] = None
    updated_by_id:  Optional[int] = None
    children:       list[MergedChildResponse] = []
    model_config = {"from_attributes": True}


# ─── Output Type ──────────────────────────────────────────────────────────────
class OutputTypeCreate(BaseModel):
    code:            str
    name:            str
    category:        str
    is_good_product: bool           = False
    sort_order:      int            = 0
    remarks:         Optional[str]  = None


class OutputTypeUpdate(BaseModel):
    name:            Optional[str]  = None
    category:        Optional[str]  = None
    is_good_product: Optional[bool] = None
    sort_order:      Optional[int]  = None
    remarks:         Optional[str]  = None
    is_active:       Optional[bool] = None


class OutputTypeResponse(BaseModel):
    id:              int
    code:            str
    name:            str
    category:        str
    is_good_product: bool
    sort_order:      int
    remarks:         Optional[str]
    is_active:       bool
    created_at:      datetime
    created_by_id:   Optional[int]
    model_config = {"from_attributes": True}