"""
input.py (schemas)
──────────────────
Pydantic schemas untuk endpoint input data transaksional OEE.
"""

from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from datetime import datetime


class ProductionOutputCreate(BaseModel):
    date:               datetime
    line_id:            int
    shift_id:           int
    feed_code_id:       Optional[int]  = None
    production_plan:    Optional[int]  = None
    finished_goods:     int            = 0
    downgraded_product: int            = 0
    wip:                int            = 0
    remix:              int            = 0
    reject_product:     int            = 0
    remarks:            Optional[str]  = None

    @model_validator(mode="after")
    def all_non_negative(self) -> "ProductionOutputCreate":
        for field in ("finished_goods", "downgraded_product", "wip", "remix", "reject_product"):
            if getattr(self, field) < 0:
                raise ValueError(f"{field} tidak boleh negatif")
        return self


class ProductionOutputUpdate(BaseModel):
    date:               Optional[datetime] = None
    line_id:            Optional[int]      = None
    shift_id:           Optional[int]      = None
    feed_code_id:       Optional[int]      = None
    production_plan:    Optional[int]      = None
    finished_goods:     Optional[int]      = None
    downgraded_product: Optional[int]      = None
    wip:                Optional[int]      = None
    remix:              Optional[int]      = None
    reject_product:     Optional[int]      = None
    remarks:            Optional[str]      = None


class ProductionOutputResponse(BaseModel):
    """
    Flattened group response — represents the 5 rows sharing one group_id
    as a single object so the frontend UI does not need to change.
    `id` here is the group_id (string UUID).
    """
    id:                 str             # group_id — used for edit/delete
    date:               datetime
    line_id:            int
    shift_id:           int
    feed_code_id:       Optional[int]
    production_plan:    Optional[int]
    finished_goods:     int = 0
    downgraded_product: int = 0
    wip:                int = 0
    remix:              int = 0
    reject_product:     int = 0
    # computed aggregates
    actual_output:      int = 0
    good_product:       int = 0
    quality_rate:       float = 0.0
    remarks:            Optional[str]
    is_active:          bool
    created_at:         datetime
    created_by_id:      Optional[int]
    # Embedded names
    line_name:          Optional[str] = None
    shift_name:         Optional[str] = None
    feed_code_code:     Optional[str] = None

    model_config = {"from_attributes": False}


# ─── Machine Loss Input ───────────────────────────────────────────────────────

class MachineLossInputCreate(BaseModel):
    date:             datetime
    line_id:          int
    shift_id:         int
    feed_code_id:     Optional[int]   = None
    loss_l1_id:       Optional[int]   = None
    loss_l2_id:       Optional[int]   = None
    loss_l3_id:       Optional[int]   = None
    time_from:        Optional[str]   = None   # HH:MM
    time_to:          Optional[str]   = None   # HH:MM
    duration_minutes: float
    remarks:          Optional[str]   = None

    @field_validator("duration_minutes")
    @classmethod
    def duration_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("duration_minutes must be greater than 0")
        return v


class MachineLossInputUpdate(BaseModel):
    date:             Optional[datetime] = None
    line_id:          Optional[int]      = None
    shift_id:         Optional[int]      = None
    feed_code_id:     Optional[int]      = None
    loss_l1_id:       Optional[int]      = None
    loss_l2_id:       Optional[int]      = None
    loss_l3_id:       Optional[int]      = None
    time_from:        Optional[str]      = None
    time_to:          Optional[str]      = None
    duration_minutes: Optional[float]    = None
    remarks:          Optional[str]      = None


class MachineLossInputResponse(BaseModel):
    id:               int
    date:             datetime
    line_id:          int
    shift_id:         int
    feed_code_id:     Optional[int]
    loss_l1_id:       Optional[int]
    loss_l2_id:       Optional[int]
    loss_l3_id:       Optional[int]
    time_from:        Optional[str]
    time_to:          Optional[str]
    duration_minutes: float
    remarks:          Optional[str]
    is_active:        bool
    created_at:       datetime
    created_by_id:    Optional[int]
    # Denormalised display fields
    line_name:        Optional[str] = None
    shift_name:       Optional[str] = None
    feed_code_code:   Optional[str] = None
    loss_l1_name:     Optional[str] = None
    loss_l2_name:     Optional[str] = None
    loss_l3_name:     Optional[str] = None

    model_config = {"from_attributes": True}
