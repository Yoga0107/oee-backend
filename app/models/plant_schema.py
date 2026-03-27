from datetime import datetime, time
from sqlalchemy import (
    Integer, String, Boolean, DateTime, Time, Float, ForeignKey,
    UniqueConstraint, func, Text, SmallInteger
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase


class PlantBase(DeclarativeBase):
    pass


# ─── Loss Level 1 ─────────────────────────────────────────
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


# ─── Loss Level 2 ──────────────────────────────────────────
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


# ─── Loss Level 3 ───────────────────────────────────────────
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


# ─── Master Machine Losses Level 1 ──────────────────────────────────────────
class MachineLossLvl1(PlantBase):
    """master_machine_losses_lvl_1 — top-level loss category."""
    __tablename__ = "master_machine_losses_lvl_1"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:          Mapped[str]       = mapped_column(String(200), nullable=False)
    description:   Mapped[str|None]  = mapped_column(Text)
    sort_order:    Mapped[int]       = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    # children in lvl2
    lvl2_children: Mapped[list["MachineLossLvl2"]] = relationship(
        "MachineLossLvl2", back_populates="lvl1",
        order_by="MachineLossLvl2.sort_order",
    )


# ─── Master Machine Losses Level 2 ──────────────────────────────────────────
class MachineLossLvl2(PlantBase):
    """master_machine_losses_lvl_2 — sub-category loss."""
    __tablename__ = "master_machine_losses_lvl_2"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    lvl1_id:       Mapped[int]       = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_1.id", ondelete="RESTRICT"), nullable=False)
    name:          Mapped[str]       = mapped_column(String(200), nullable=False)
    description:   Mapped[str|None]  = mapped_column(Text)
    sort_order:    Mapped[int]       = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    lvl1:          Mapped["MachineLossLvl1"]         = relationship("MachineLossLvl1", back_populates="lvl2_children")
    lvl3_children: Mapped[list["MachineLossLvl3"]]   = relationship(
        "MachineLossLvl3", back_populates="lvl2",
        order_by="MachineLossLvl3.sort_order",
    )


# ─── Master Machine Losses Level 3 ──────────────────────────────────────────
class MachineLossLvl3(PlantBase):
    """master_machine_losses_lvl_3 — detail loss."""
    __tablename__ = "master_machine_losses_lvl_3"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    lvl2_id:       Mapped[int]       = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_2.id", ondelete="RESTRICT"), nullable=False)
    name:          Mapped[str]       = mapped_column(String(200), nullable=False)
    description:   Mapped[str|None]  = mapped_column(Text)
    sort_order:    Mapped[int]       = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    lvl2: Mapped["MachineLossLvl2"] = relationship("MachineLossLvl2", back_populates="lvl3_children")


# ─── Master Machine Losses (katalog kombinasi L1+L2+L3) ─────────────────────
class MasterMachineLoss(PlantBase):
    """
    master_machine_losses — katalog kombinasi loss.
    Setiap baris menyimpan FK ke L1 (wajib), L2 (opsional), L3 (opsional)
    sesuai ERD referensi.
    """
    __tablename__ = "master_machine_losses"

    id:               Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    lvl1_id:          Mapped[int]      = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_1.id", ondelete="RESTRICT"), nullable=False)
    lvl2_id:          Mapped[int|None] = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_2.id", ondelete="RESTRICT"), nullable=True)
    lvl3_id:          Mapped[int|None] = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_3.id", ondelete="RESTRICT"), nullable=True)
    remarks:          Mapped[str|None] = mapped_column(Text)
    is_active:        Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id:    Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:       Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:    Mapped[int|None] = mapped_column(Integer, nullable=True)

    lvl1: Mapped["MachineLossLvl1"]       = relationship("MachineLossLvl1", foreign_keys=[lvl1_id])
    lvl2: Mapped["MachineLossLvl2|None"]  = relationship("MachineLossLvl2", foreign_keys=[lvl2_id])
    lvl3: Mapped["MachineLossLvl3|None"]  = relationship("MachineLossLvl3", foreign_keys=[lvl3_id])


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


# ─── Production Output ───────────────────────────────────────────────────────
# ─── Production Output type & category mapping ───────────────────────────────
OUTPUT_TYPE_CATEGORY: dict[str, str] = {
    "finished_goods":     "FG",
    "downgraded_product": "DOWNGRADED",
    "wip":                "WIP",
    "remix":              "REMIX",
    "reject_product":     "REJECT",
}
OUTPUT_TYPES = tuple(OUTPUT_TYPE_CATEGORY.keys())


class ProductionOutput(PlantBase):
    """
    Production output — one row per output_type per submission.
    1 form submit (with 5 qty fields) creates 5 rows sharing the same group_id.
    group_id is used to fetch/edit/delete all 5 rows together.
    """
    __tablename__ = "production_outputs"

    id:              Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id:        Mapped[str]       = mapped_column(String(36), nullable=False, index=True)  # UUID — ties 5 rows together
    date:            Mapped[datetime]  = mapped_column(DateTime, nullable=False)
    line_id:         Mapped[int]       = mapped_column(Integer, ForeignKey("master_lines.id", ondelete="RESTRICT"), nullable=False)
    shift_id:        Mapped[int]       = mapped_column(Integer, ForeignKey("master_shifts.id", ondelete="RESTRICT"), nullable=False)
    feed_code_id:    Mapped[int|None]  = mapped_column(Integer, ForeignKey("master_feed_codes.id", ondelete="SET NULL"), nullable=True)
    production_plan: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    output_type:     Mapped[str]       = mapped_column(String(50), nullable=False)   # finished_goods | downgraded_product | wip | remix | reject_product
    category:        Mapped[str]       = mapped_column(String(50), nullable=False)   # FG | DOWNGRADED | WIP | REMIX | REJECT
    quantity:        Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    remarks:         Mapped[str|None]  = mapped_column(String(500))
    is_active:       Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:      Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id:   Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:      Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:   Mapped[int|None]  = mapped_column(Integer, nullable=True)

    line:      Mapped["MasterLine"]          = relationship("MasterLine")
    shift:     Mapped["MasterShift"]         = relationship("MasterShift")
    feed_code: Mapped["MasterFeedCode|None"] = relationship("MasterFeedCode")


# ─── Machine Loss Input ───────────────────────────────────────────────────────
class MachineLossInput(PlantBase):
    """
    Transactional downtime entry per shift per line.
    References machine_losses (L1/L2/L3) for loss categorisation.
    Duration is stored in minutes; time_from/time_to are optional exact timestamps.
    """
    __tablename__ = "machine_loss_inputs"

    id:               Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    date:             Mapped[datetime]  = mapped_column(DateTime, nullable=False)
    line_id:          Mapped[int]       = mapped_column(Integer, ForeignKey("master_lines.id",  ondelete="RESTRICT"), nullable=False)
    shift_id:         Mapped[int]       = mapped_column(Integer, ForeignKey("master_shifts.id", ondelete="RESTRICT"), nullable=False)
    feed_code_id:     Mapped[int|None]  = mapped_column(Integer, ForeignKey("master_feed_codes.id", ondelete="SET NULL"), nullable=True)
    # Loss category — FK ke tabel level terpisah sesuai ERD
    loss_l1_id:       Mapped[int|None]  = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_1.id", ondelete="RESTRICT"), nullable=True)
    loss_l2_id:       Mapped[int|None]  = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_2.id", ondelete="RESTRICT"), nullable=True)
    loss_l3_id:       Mapped[int|None]  = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_3.id", ondelete="RESTRICT"), nullable=True)
    # Time window (optional exact timestamps)
    time_from:        Mapped[str|None]  = mapped_column(String(8))   # HH:MM:SS
    time_to:          Mapped[str|None]  = mapped_column(String(8))
    # Duration in minutes — required; computed from time_from/time_to when provided
    duration_minutes: Mapped[float]     = mapped_column(Float, nullable=False)
    remarks:          Mapped[str|None]  = mapped_column(String(500))
    is_active:        Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:       Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id:    Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:       Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:    Mapped[int|None]  = mapped_column(Integer, nullable=True)

    line:      Mapped["MasterLine"]              = relationship("MasterLine")
    shift:     Mapped["MasterShift"]             = relationship("MasterShift")
    feed_code: Mapped["MasterFeedCode|None"]     = relationship("MasterFeedCode")
    loss_l1:   Mapped["MachineLossLvl1|None"]    = relationship("MachineLossLvl1", foreign_keys=[loss_l1_id])
    loss_l2:   Mapped["MachineLossLvl2|None"]    = relationship("MachineLossLvl2", foreign_keys=[loss_l2_id])
    loss_l3:   Mapped["MachineLossLvl3|None"]    = relationship("MachineLossLvl3", foreign_keys=[loss_l3_id])


# ─── Merged Line ──────────────────────────────────────────────────────────────
class MergedLine(PlantBase):
    """
    Gabungan dari beberapa master_line yang diperlakukan sebagai satu entitas.
    Misalnya Line 1 + Line 2 digabung menjadi 'Line Gabungan A'.
    """
    __tablename__ = "merged_lines"

    id:            Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:          Mapped[str]       = mapped_column(String(100), nullable=False)
    code:          Mapped[str|None]  = mapped_column(String(50))
    remarks:       Mapped[str|None]  = mapped_column(String(500))
    is_active:     Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime]  = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None]  = mapped_column(Integer, nullable=True)

    details: Mapped[list["MergedLineDetail"]] = relationship(
        "MergedLineDetail", back_populates="merged_line", cascade="all, delete-orphan"
    )


class MergedLineDetail(PlantBase):
    """Setiap baris = satu master_line anggota dari merged_line."""
    __tablename__ = "merged_line_details"

    merged_line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("merged_lines.id", ondelete="CASCADE"), primary_key=True
    )
    line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("master_lines.id", ondelete="CASCADE"), primary_key=True
    )

    merged_line: Mapped["MergedLine"] = relationship("MergedLine", back_populates="details")
    line:        Mapped["MasterLine"] = relationship("MasterLine")
