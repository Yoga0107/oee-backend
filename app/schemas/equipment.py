

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EquipmentTreeCreate(BaseModel):
    sistem:      str
    sub_sistem:  Optional[str] = None
    unit_mesin:  Optional[str] = None
    bagian_mesin: Optional[str] = None
    spare_part:  Optional[str] = None
    spesifikasi: Optional[str] = None
    sku:         Optional[str] = None
    bu:          Optional[str] = None
    remarks:     Optional[str] = None


class EquipmentTreeUpdate(BaseModel):
    sistem:      Optional[str] = None
    sub_sistem:  Optional[str] = None
    unit_mesin:  Optional[str] = None
    bagian_mesin: Optional[str] = None
    spare_part:  Optional[str] = None
    spesifikasi: Optional[str] = None
    sku:         Optional[str] = None
    bu:          Optional[str] = None
    remarks:     Optional[str] = None
    is_active:   Optional[bool] = None


class EquipmentTreeResponse(BaseModel):
    id:             int
    sistem:         str
    sub_sistem:     Optional[str]
    unit_mesin:     Optional[str]
    bagian_mesin:   Optional[str]
    spare_part:     Optional[str]
    spesifikasi:    Optional[str]
    sku:            Optional[str]
    bu:             Optional[str]
    is_verified:    bool
    verified_by_id: Optional[int]
    verified_at:    Optional[datetime]
    remarks:        Optional[str]
    is_active:      bool
    created_at:     datetime
    created_by_id:  Optional[int]
    updated_at:     datetime

    model_config = {"from_attributes": True}
