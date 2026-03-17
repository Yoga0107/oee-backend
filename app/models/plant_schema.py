"""
Plant-schema models.
Each plant gets its own PostgreSQL schema with these tables.

Arsitektur Machine Loss:
  loss_level_1  → tabel master input L1 (Loss Category)
  loss_level_2  → tabel master input L2 (Sub Category, FK → loss_level_1)
  loss_level_3  → tabel master input L3 (Detail Loss, FK → loss_level_2)
  machine_losses → tabel agregasi tersendiri, disync dari loss_level_1/2/3
                   (via trigger PostgreSQL atau endpoint /sync manual)
  machine_loss_hierarchy → tabel transaksional drag-and-drop remap,
                           FK langsung ke loss_level_1/2/3
"""
from datetime import datetime, time
from sqlalchemy import (
    Integer, String, Boolean, DateTime, Time, ForeignKey,
    UniqueConstraint, func, Text, SmallInteger
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase


class PlantBase(DeclarativeBase):
    pass


# ─── Loss Level 1 (Loss Category) ─────────────────────────────────────────
class LossLevel1(PlantBase):
    __tablename__ = "loss_level_1"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:          Mapped[str]       = mapped_column(String(200), nullable=False)
    description:   Mapped[str|None]  = mapped_column(Text)
    sort_order:    Mapped[int]       = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    children: Mapped[list["LossLevel2"]] = relationship(
        "LossLevel2", back_populates="level1",
        order_by="LossLevel2.sort_order",
    )


# ─── Loss Level 2 (Sub Category) ──────────────────────────────────────────
class LossLevel2(PlantBase):
    __tablename__ = "loss_level_2"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    level_1_id:    Mapped[int]       = mapped_column(Integer, ForeignKey("loss_level_1.id", ondelete="RESTRICT"), nullable=False)
    name:          Mapped[str]       = mapped_column(String(200), nullable=False)
    description:   Mapped[str|None]  = mapped_column(Text)
    sort_order:    Mapped[int]       = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    level1:   Mapped["LossLevel1"]       = relationship("LossLevel1", back_populates="children")
    children: Mapped[list["LossLevel3"]] = relationship(
        "LossLevel3", back_populates="level2",
        order_by="LossLevel3.sort_order",
    )


# ─── Loss Level 3 (Detail Loss) ───────────────────────────────────────────
class LossLevel3(PlantBase):
    __tablename__ = "loss_level_3"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    level_2_id:    Mapped[int]       = mapped_column(Integer, ForeignKey("loss_level_2.id", ondelete="RESTRICT"), nullable=False)
    name:          Mapped[str]       = mapped_column(String(200), nullable=False)
    description:   Mapped[str|None]  = mapped_column(Text)
    sort_order:    Mapped[int]       = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    level2: Mapped["LossLevel2"] = relationship("LossLevel2", back_populates="children")


# ─── Machine Losses (agregasi tersendiri, disync dari loss_level_1/2/3) ───
class MachineLoss(PlantBase):
    """
    Tabel self-referencing tunggal untuk semua level machine loss.
    - level 1: parent_id IS NULL
    - level 2: parent_id → machine_losses.id level 1
    - level 3: parent_id → machine_losses.id level 2

    Ini adalah tabel yang dipakai langsung oleh master page tree + drag-and-drop.
    Memindah node = update parent_id + level. ID tidak pernah berubah.
    """
    __tablename__ = "machine_losses"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id:     Mapped[int|None]  = mapped_column(Integer, ForeignKey("machine_losses.id", ondelete="RESTRICT"), nullable=True)
    level:         Mapped[int]       = mapped_column(SmallInteger, nullable=False)   # 1 | 2 | 3
    name:          Mapped[str]       = mapped_column(String(200), nullable=False)
    description:   Mapped[str|None]  = mapped_column(Text)
    sort_order:    Mapped[int]       = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    children: Mapped[list["MachineLoss"]] = relationship(
        "MachineLoss", back_populates="parent",
        foreign_keys="MachineLoss.parent_id",
        order_by="MachineLoss.sort_order",
    )
    parent: Mapped["MachineLoss|None"] = relationship(
        "MachineLoss", back_populates="children",
        foreign_keys="MachineLoss.parent_id",
        remote_side="MachineLoss.id",
    )


# ─── Machine Loss Hierarchy (transaksional drag-and-drop remap) ───────────
class MachineLossHierarchy(PlantBase):
    """
    Tabel transaksional re-mapping hierarki machine loss.

    FK langsung ke loss_level_1/2/3 (tepat satu yang non-null sesuai source_level).
    effective_level bisa berbeda dari source_level (hasil drag promosi/demosi).
    parent_hierarchy_id → self-FK ke row lain dalam tabel ini.
    is_unparented → True jika parent-nya dipindah dan node ini jadi orphan.
    """
    __tablename__ = "machine_loss_hierarchy"

    id:                  Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Sumber: tepat satu non-null
    source_level:        Mapped[int]      = mapped_column(SmallInteger, nullable=False)   # 1 | 2 | 3
    level_1_id:          Mapped[int|None] = mapped_column(Integer, ForeignKey("loss_level_1.id", ondelete="CASCADE"), nullable=True)
    level_2_id:          Mapped[int|None] = mapped_column(Integer, ForeignKey("loss_level_2.id", ondelete="CASCADE"), nullable=True)
    level_3_id:          Mapped[int|None] = mapped_column(Integer, ForeignKey("loss_level_3.id", ondelete="CASCADE"), nullable=True)
    source_name:         Mapped[str]      = mapped_column(String(200), nullable=False)    # cache nama (denormalized)
    # Level efektif dalam tampilan hierarchy
    effective_level:     Mapped[int]      = mapped_column(SmallInteger, nullable=False)
    # Parent dalam hierarchy ini (self-FK)
    parent_hierarchy_id: Mapped[int|None] = mapped_column(
        Integer, ForeignKey("machine_loss_hierarchy.id", ondelete="SET NULL"), nullable=True
    )
    sort_order:          Mapped[int]      = mapped_column(Integer, default=0)
    is_unparented:       Mapped[bool]     = mapped_column(Boolean, default=False)
    notes:               Mapped[str|None] = mapped_column(String(500))
    is_active:           Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:          Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id:       Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:          Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:       Mapped[int|None] = mapped_column(Integer, nullable=True)

    # FK ke tabel sumber
    level1_ref: Mapped["LossLevel1|None"] = relationship("LossLevel1", foreign_keys=[level_1_id])
    level2_ref: Mapped["LossLevel2|None"] = relationship("LossLevel2", foreign_keys=[level_2_id])
    level3_ref: Mapped["LossLevel3|None"] = relationship("LossLevel3", foreign_keys=[level_3_id])
    # Self-referencing hierarchy
    parent: Mapped["MachineLossHierarchy|None"] = relationship(
        "MachineLossHierarchy", back_populates="children",
        foreign_keys=[parent_hierarchy_id], remote_side="MachineLossHierarchy.id",
    )
    children: Mapped[list["MachineLossHierarchy"]] = relationship(
        "MachineLossHierarchy", back_populates="parent",
        foreign_keys=[parent_hierarchy_id], order_by="MachineLossHierarchy.sort_order",
    )


# ─── Shift ──────────────────────────────────────────────────────────────────
class MasterShift(PlantBase):
    __tablename__ = "master_shifts"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:          Mapped[str]       = mapped_column(String(50), nullable=False)
    time_from:     Mapped[time]      = mapped_column(Time, nullable=False)
    time_to:       Mapped[time]      = mapped_column(Time, nullable=False)
    remarks:       Mapped[str|None]  = mapped_column(String(500))
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)


# ─── Feed Code ──────────────────────────────────────────────────────────────
class MasterFeedCode(PlantBase):
    __tablename__ = "master_feed_codes"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    code:          Mapped[str]       = mapped_column(String(50), unique=True, nullable=False)
    remarks:       Mapped[str|None]  = mapped_column(String(500))
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    standard_throughputs: Mapped[list["MasterStandardThroughput"]] = relationship(
        "MasterStandardThroughput", back_populates="feed_code"
    )


# ─── Line ────────────────────────────────────────────────────────────────────
class MasterLine(PlantBase):
    __tablename__ = "master_lines"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id:      Mapped[int]       = mapped_column(Integer, nullable=False)
    name:          Mapped[str]       = mapped_column(String(100), nullable=False)
    code:          Mapped[str|None]  = mapped_column(String(50))
    remarks:       Mapped[str|None]  = mapped_column(String(500))
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    standard_throughputs: Mapped[list["MasterStandardThroughput"]] = relationship(
        "MasterStandardThroughput", back_populates="line"
    )


# ─── Standard Throughput ─────────────────────────────────────────────────────
class MasterStandardThroughput(PlantBase):
    __tablename__ = "master_standard_throughputs"
    __table_args__ = (UniqueConstraint("line_id", "feed_code_id", name="uq_line_feedcode"),)

    id:                  Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_id:             Mapped[int]       = mapped_column(Integer, ForeignKey("master_lines.id"), nullable=False)
    feed_code_id:        Mapped[int]       = mapped_column(Integer, ForeignKey("master_feed_codes.id"), nullable=False)
    standard_throughput: Mapped[int]       = mapped_column(Integer, nullable=False)
    remarks:             Mapped[str|None]  = mapped_column(String(500))
    created_at:          Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id:       Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:          Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:       Mapped[int|None]  = mapped_column(Integer, nullable=True)

    line:      Mapped["MasterLine"]     = relationship("MasterLine", back_populates="standard_throughputs")
    feed_code: Mapped["MasterFeedCode"] = relationship("MasterFeedCode", back_populates="standard_throughputs")
