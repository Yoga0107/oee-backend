"""
Plant-schema models.
Each plant gets its own PostgreSQL schema with these tables.
"""
from datetime import datetime, time
from sqlalchemy import (
    Integer, String, Boolean, DateTime, Time, ForeignKey,
    UniqueConstraint, func, Text, SmallInteger
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase


class PlantBase(DeclarativeBase):
    pass


# ─── Machine Loss (unified self-referencing table) ─────────────────────────
class MachineLoss(PlantBase):
    """
    Single self-referencing table for all loss levels.
    - level 1: parent_id IS NULL
    - level 2: parent_id → level 1 id
    - level 3: parent_id → level 2 id
    Moving a node = just update parent_id + level. ID never changes.
    """
    __tablename__ = "machine_losses"

    id:          Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id:   Mapped[int|None]  = mapped_column(Integer, ForeignKey("machine_losses.id", ondelete="RESTRICT"), nullable=True)
    level:       Mapped[int]       = mapped_column(SmallInteger, nullable=False)  # 1 | 2 | 3
    name:        Mapped[str]       = mapped_column(String(200), nullable=False)
    description: Mapped[str|None]  = mapped_column(Text)
    sort_order:  Mapped[int]       = mapped_column(Integer, default=0)
    is_active:   Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:  Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:  Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)

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


# ─── Shift ──────────────────────────────────────────────────────────────────
class MasterShift(PlantBase):
    __tablename__ = "master_shifts"

    id:         Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:       Mapped[str]       = mapped_column(String(50), nullable=False)
    time_from:  Mapped[time]      = mapped_column(Time, nullable=False)
    time_to:    Mapped[time]      = mapped_column(Time, nullable=False)
    remarks:    Mapped[str|None]  = mapped_column(String(500))
    is_active:  Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)


# ─── Feed Code ──────────────────────────────────────────────────────────────
class MasterFeedCode(PlantBase):
    __tablename__ = "master_feed_codes"

    id:         Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    code:       Mapped[str]       = mapped_column(String(50), unique=True, nullable=False)
    remarks:    Mapped[str|None]  = mapped_column(String(500))
    is_active:  Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)

    standard_throughputs: Mapped[list["MasterStandardThroughput"]] = relationship(
        "MasterStandardThroughput", back_populates="feed_code"
    )


# ─── Line ────────────────────────────────────────────────────────────────────
class MasterLine(PlantBase):
    __tablename__ = "master_lines"

    id:       Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[int]      = mapped_column(Integer, nullable=False)
    name:     Mapped[str]      = mapped_column(String(100), nullable=False)
    code:     Mapped[str|None] = mapped_column(String(50))
    remarks:  Mapped[str|None] = mapped_column(String(500))
    is_active: Mapped[bool]    = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)

    standard_throughputs: Mapped[list["MasterStandardThroughput"]] = relationship(
        "MasterStandardThroughput", back_populates="line"
    )


# ─── Standard Throughput ─────────────────────────────────────────────────────
class MasterStandardThroughput(PlantBase):
    __tablename__ = "master_standard_throughputs"
    __table_args__ = (
        UniqueConstraint("line_id", "feed_code_id", name="uq_line_feedcode"),
    )

    id:                   Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_id:              Mapped[int]      = mapped_column(Integer, ForeignKey("master_lines.id"), nullable=False)
    feed_code_id:         Mapped[int]      = mapped_column(Integer, ForeignKey("master_feed_codes.id"), nullable=False)
    standard_throughput:  Mapped[int]      = mapped_column(Integer, nullable=False)
    remarks:              Mapped[str|None] = mapped_column(String(500))
    created_at:           Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id:        Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:           Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:        Mapped[int|None] = mapped_column(Integer, nullable=True)

    line:      Mapped["MasterLine"]     = relationship("MasterLine", back_populates="standard_throughputs")
    feed_code: Mapped["MasterFeedCode"] = relationship("MasterFeedCode", back_populates="standard_throughputs")
