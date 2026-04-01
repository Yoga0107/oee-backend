"""
input.py (schemas)
──────────────────
Pydantic schemas untuk endpoint input data transaksional OEE.
"""

from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


# ─── Production Output ────────────────────────────────────────────────────────

class ProductionOutputCreate(BaseModel):
    date:            datetime
    line_id:         int
    shift_id:        int
    feed_code_id:    Optional[int]        = None
    production_plan: Optional[int]        = None
    quantities:      dict[str, int]       = {}   # {output_type_code: quantity}
    remarks:         Optional[str]        = None

    @field_validator("quantities")
    @classmethod
    def quantities_non_negative(cls, v: dict) -> dict:
        for k, qty in v.items():
            if qty < 0:
                raise ValueError(f"Quantity untuk '{k}' tidak boleh negatif")
        return v


class ProductionOutputUpdate(BaseModel):
    date:            Optional[datetime]       = None
    line_id:         Optional[int]            = None
    shift_id:        Optional[int]            = None
    feed_code_id:    Optional[int]            = None
    production_plan: Optional[int]            = None
    quantities:      Optional[dict[str, int]] = None
    remarks:         Optional[str]            = None


class ProductionOutputResponse(BaseModel):
    id:              str                  # group_id
    date:            datetime
    line_id:         int
    shift_id:        int
    feed_code_id:    Optional[int]
    production_plan: Optional[int]
    # Quantities dinamis dari master_output_types {code: quantity}
    quantities:      dict[str, int]       = {}
    # Computed
    actual_output:   int                  = 0
    remarks:         Optional[str]
    is_active:       bool
    created_at:      datetime
    created_by_id:   Optional[int]
    # Embedded names (denormalized untuk display)
    line_name:       Optional[str]        = None
    shift_name:      Optional[str]        = None
    feed_code_code:  Optional[str]        = None

    model_config = {"from_attributes": True}


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
