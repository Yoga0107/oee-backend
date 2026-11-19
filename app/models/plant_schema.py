from datetime import datetime, time
from sqlalchemy import (  # type: ignore[reportMissingImports]
    Integer, String, Boolean, DateTime, Time, Float, ForeignKey,
    UniqueConstraint, func, Text, SmallInteger
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase  # type: ignore[reportMissingImports]


class PlantBase(DeclarativeBase):
    pass


# ─── Master Machine Losses Level 1 ──────────────────────────────────────────
class MachineLossLvl1(PlantBase):
    """master_machine_losses_lvl_1 — flat, no FK to other levels."""
    __tablename__ = "master_machine_losses_lvl_1"

    machine_losses_lvl_1_id: Mapped[int] = mapped_column("machine_losses_lvl_1_id", Integer, primary_key=True, autoincrement=True)
    name:                    Mapped[str] = mapped_column(String(200), nullable=False)


# ─── Master Machine Losses Level 2 ──────────────────────────────────────────
class MachineLossLvl2(PlantBase):
    """master_machine_losses_lvl_2 — flat, no FK to lvl1."""
    __tablename__ = "master_machine_losses_lvl_2"

    machine_losses_lvl_2_id: Mapped[int] = mapped_column("machine_losses_lvl_2_id", Integer, primary_key=True, autoincrement=True)
    name:                    Mapped[str] = mapped_column(String(200), nullable=False)


# ─── Master Machine Losses Level 3 ──────────────────────────────────────────
class MachineLossLvl3(PlantBase):
    """master_machine_losses_lvl_3 — flat, no FK to lvl2."""
    __tablename__ = "master_machine_losses_lvl_3"

    machine_losses_lvl_3_id: Mapped[int] = mapped_column("machine_losses_lvl_3_id", Integer, primary_key=True, autoincrement=True)
    name:                    Mapped[str] = mapped_column(String(200), nullable=False)


# ─── Master Machine Losses (hierarki ada di sini) ───────────────────────────
class MasterMachineLoss(PlantBase):
    """
    master_machine_losses — katalog kombinasi loss.
    Hierarki L1 -> L2 -> L3 direpresentasikan di sini via FK.
    Setiap baris = satu kombinasi loss yang valid.
    """
    __tablename__ = "master_machine_losses"

    machine_losses_id:       Mapped[int]      = mapped_column("machine_losses_id", Integer, primary_key=True, autoincrement=True)
    machine_losses_lvl_1_id: Mapped[int]      = mapped_column("machine_losses_lvl_1_id", Integer, ForeignKey("master_machine_losses_lvl_1.machine_losses_lvl_1_id", ondelete="RESTRICT"), nullable=False)
    machine_losses_lvl_2_id: Mapped[int|None] = mapped_column("machine_losses_lvl_2_id", Integer, ForeignKey("master_machine_losses_lvl_2.machine_losses_lvl_2_id", ondelete="RESTRICT"), nullable=True)
    machine_losses_lvl_3_id: Mapped[int|None] = mapped_column("machine_losses_lvl_3_id", Integer, ForeignKey("master_machine_losses_lvl_3.machine_losses_lvl_3_id", ondelete="RESTRICT"), nullable=True)
    remarks:                 Mapped[str|None] = mapped_column(Text)
    is_active:               Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:              Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id:           Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:              Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:           Mapped[int|None] = mapped_column(Integer, nullable=True)

    lvl1: Mapped["MachineLossLvl1"]      = relationship("MachineLossLvl1", foreign_keys=[machine_losses_lvl_1_id])
    lvl2: Mapped["MachineLossLvl2|None"] = relationship("MachineLossLvl2", foreign_keys=[machine_losses_lvl_2_id])
    lvl3: Mapped["MachineLossLvl3|None"] = relationship("MachineLossLvl3", foreign_keys=[machine_losses_lvl_3_id])


# ─── Shift ──────────────────────────────────────────────────────────────────
class MasterShift(PlantBase):
    __tablename__ = "master_shifts"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    name:          Mapped[str]      = mapped_column(String(50), nullable=False)
    time_from:     Mapped[time]     = mapped_column(Time, nullable=False)
    time_to:       Mapped[time]     = mapped_column(Time, nullable=False)
    remarks:       Mapped[str|None] = mapped_column(String(500))
    is_active:     Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)


# ─── Feed Code ──────────────────────────────────────────────────────────────
class MasterFeedCode(PlantBase):
    __tablename__ = "master_feed_codes"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    code:          Mapped[str]      = mapped_column(String(50), unique=True, nullable=False)
    remarks:       Mapped[str|None] = mapped_column(String(500))
    is_active:     Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)

    standard_throughputs: Mapped[list["MasterStandardThroughput"]] = relationship(
        "MasterStandardThroughput", back_populates="feed_code"
    )


# ─── Line ────────────────────────────────────────────────────────────────────
# MODIFIKASI: Menambahkan kolom `type` untuk membedakan line fisik vs hasil merge.
# Semua line (fisik maupun gabungan) disimpan di tabel ini.
# Relasi penggabungan (termasuk bertingkat) dikelola via IntLineMerge.
LINE_TYPE_PHYSICAL = "physical"   # Line fisik / asli
LINE_TYPE_MERGED   = "merged"     # Line hasil penggabungan
 
 
class MasterLine(PlantBase):
    __tablename__ = "master_lines"
 
    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id:      Mapped[int]      = mapped_column(Integer, nullable=False)
    name:          Mapped[str]      = mapped_column(String(100), nullable=False)
    type:          Mapped[str]      = mapped_column(String(20), nullable=False, default=LINE_TYPE_PHYSICAL)
    # type: 'physical' = line asli/fisik, 'merged' = line hasil penggabungan
    code:          Mapped[str|None] = mapped_column(String(50))
    remarks:       Mapped[str|None] = mapped_column(String(500))
    is_active:     Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
 
    standard_throughputs: Mapped[list["MasterStandardThroughput"]] = relationship(
        "MasterStandardThroughput", back_populates="line"
    )
 
    # Relasi sebagai parent (line ini adalah hasil merge dari children di bawahnya)
    child_merges: Mapped[list["IntLineMerge"]] = relationship(
        "IntLineMerge",
        foreign_keys="IntLineMerge.parent_line_id",
        back_populates="parent_line",
        cascade="all, delete-orphan",
    )
 
    # Relasi sebagai child (line ini adalah anggota dari suatu merged line)
    parent_merges: Mapped[list["IntLineMerge"]] = relationship(
        "IntLineMerge",
        foreign_keys="IntLineMerge.child_line_id",
        back_populates="child_line",
    )
 
 
# ─── Int Line Merge ───────────────────────────────────────────────────────────
# BARU: Menggantikan merged_lines + merged_line_details.
# Self-referential many-to-many pada master_lines.
# Mendukung penggabungan bertingkat:
#   LINE_AB  → {LINE_A, LINE_B}
#   LINE_CD  → {LINE_C, LINE_D}
#   LINE_ABCD → {LINE_AB, LINE_CD}   ← parent/child keduanya bertipe 'merged'
class IntLineMerge(PlantBase):
    """
    int_line_merge — tabel relasi penggabungan line (self-referential).
 
    parent_line_id : line hasil penggabungan (type = 'merged')
    child_line_id  : line anggota (type = 'physical' ATAU 'merged')
 
    Contoh penggabungan bertingkat:
      INSERT (parent=LINE_AB,   child=LINE_A)
      INSERT (parent=LINE_AB,   child=LINE_B)
      INSERT (parent=LINE_CD,   child=LINE_C)
      INSERT (parent=LINE_CD,   child=LINE_D)
      INSERT (parent=LINE_ABCD, child=LINE_AB)   ← child adalah merged line
      INSERT (parent=LINE_ABCD, child=LINE_CD)   ← child adalah merged line
    """
    __tablename__ = "int_line_merge"
    __table_args__ = (
        UniqueConstraint("parent_line_id", "child_line_id", name="uq_line_merge_parent_child"),
    )
 
    parent_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("master_lines.id", ondelete="CASCADE"),
        primary_key=True,
    )
    child_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("master_lines.id", ondelete="CASCADE"),
        primary_key=True,
    )
 
    parent_line: Mapped["MasterLine"] = relationship(
        "MasterLine", foreign_keys=[parent_line_id], back_populates="child_merges"
    )
    child_line: Mapped["MasterLine"] = relationship(
        "MasterLine", foreign_keys=[child_line_id], back_populates="parent_merges"
    )


# ─── Standard Throughput ─────────────────────────────────────────────────────
class MasterStandardThroughput(PlantBase):
    __tablename__ = "master_standard_throughputs"
    __table_args__ = (UniqueConstraint("line_id", "feed_code_id", name="uq_line_feedcode"),)

    id:                  Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_id:             Mapped[int]      = mapped_column(Integer, ForeignKey("master_lines.id"), nullable=False)
    feed_code_id:        Mapped[int]      = mapped_column(Integer, ForeignKey("master_feed_codes.id"), nullable=False)
    standard_throughput: Mapped[int]      = mapped_column(Integer, nullable=False)
    remarks:             Mapped[str|None] = mapped_column(String(500))
    is_active:           Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:          Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id:       Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:          Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:       Mapped[int|None] = mapped_column(Integer, nullable=True)

    line:      Mapped["MasterLine"]     = relationship("MasterLine", back_populates="standard_throughputs")
    feed_code: Mapped["MasterFeedCode"] = relationship("MasterFeedCode", back_populates="standard_throughputs")
    logs: Mapped[list["StandardThroughputLog"]] = relationship("StandardThroughputLog", back_populates="standard_throughput", order_by="StandardThroughputLog.id")


class StandardThroughputLog(PlantBase):
    __tablename__ = "standard_throughput_logs"

    id:                      Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    standard_throughput_id:  Mapped[int]      = mapped_column(Integer, ForeignKey("master_standard_throughputs.id", ondelete="CASCADE"), nullable=False)
    change_number:           Mapped[int]      = mapped_column(Integer, nullable=False)
    old_throughput:          Mapped[int|None] = mapped_column(Integer)
    new_throughput:          Mapped[int]      = mapped_column(Integer, nullable=False)
    old_remarks:             Mapped[str|None] = mapped_column(String(500))
    new_remarks:             Mapped[str|None] = mapped_column(String(500))
    reason:                  Mapped[str|None] = mapped_column(String(1000))
    changed_at:              Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    changed_by_id:           Mapped[int|None] = mapped_column(Integer, nullable=True)

    standard_throughput: Mapped["MasterStandardThroughput"] = relationship("MasterStandardThroughput", back_populates="logs")


# ─── Master Output Type ───────────────────────────────────────────────────────
class MasterOutputType(PlantBase):
    
    __tablename__ = "master_output_types"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    code:          Mapped[str]      = mapped_column(String(50), unique=True, nullable=False)
    name:          Mapped[str]      = mapped_column(String(100), nullable=False)
    category:      Mapped[str]      = mapped_column(String(50), nullable=False)
    is_good_product: Mapped[bool]   = mapped_column(Boolean, default=False)
    sort_order:    Mapped[int]      = mapped_column(Integer, default=0)
    remarks:       Mapped[str|None] = mapped_column(String(500))
    is_active:     Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id: Mapped[int|None] = mapped_column(Integer, nullable=True)


# ─── Production Output ───────────────────────────────────────────────────────
OUTPUT_TYPE_CATEGORY: dict[str, str] = {
    "finished_goods":     "FG",
    "downgraded_product": "DOWNGRADED",
    "wip":                "WIP",
    "remix":              "REMIX",
    "reject_product":     "REJECT",
}
OUTPUT_TYPES = tuple(OUTPUT_TYPE_CATEGORY.keys())

DEFAULT_OUTPUT_TYPES = [
    {"code": "finished_goods",     "name": "Finished Goods",     "category": "FG",         "is_good_product": True,  "sort_order": 1},
    {"code": "downgraded_product", "name": "Downgraded Product", "category": "DOWNGRADED", "is_good_product": False, "sort_order": 2},
    {"code": "wip",                "name": "WIP",                "category": "WIP",        "is_good_product": False, "sort_order": 3},
    {"code": "remix",              "name": "Remix",              "category": "REMIX",      "is_good_product": False, "sort_order": 4},
    {"code": "reject_product",     "name": "Reject",             "category": "REJECT",     "is_good_product": False, "sort_order": 5},
]


class ProductionOutput(PlantBase):
    __tablename__ = "production_outputs"

    id:              Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id:        Mapped[str]      = mapped_column(String(36), nullable=False, index=True)
    date:            Mapped[datetime] = mapped_column(DateTime, nullable=False)
    line_id:         Mapped[int]      = mapped_column(Integer, ForeignKey("master_lines.id", ondelete="RESTRICT"), nullable=False)
    shift_id:        Mapped[int]      = mapped_column(Integer, ForeignKey("master_shifts.id", ondelete="RESTRICT"), nullable=False)
    feed_code_id:    Mapped[int|None] = mapped_column(Integer, ForeignKey("master_feed_codes.id", ondelete="SET NULL"), nullable=True)
    production_plan: Mapped[int|None] = mapped_column(Integer, nullable=True)
    output_type:     Mapped[str]      = mapped_column(String(50), nullable=False)
    category:        Mapped[str]      = mapped_column(String(50), nullable=False)
    quantity:        Mapped[int]      = mapped_column(Integer, nullable=False, default=0)
    remarks:         Mapped[str|None] = mapped_column(String(500))
    is_active:       Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id:   Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:      Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:   Mapped[int|None] = mapped_column(Integer, nullable=True)

    line:      Mapped["MasterLine"]          = relationship("MasterLine")
    shift:     Mapped["MasterShift"]         = relationship("MasterShift")
    feed_code: Mapped["MasterFeedCode|None"] = relationship("MasterFeedCode")


# ─── Machine Loss Input ───────────────────────────────────────────────────────
class MachineLossInput(PlantBase):
    """
    Transactional downtime entry per shift per line.
    FK loss_l1/2/3_id ke master_machine_losses_lvl_1/2/3 (flat tables).
    """
    __tablename__ = "machine_loss_inputs"

    id:               Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    date:             Mapped[datetime] = mapped_column(DateTime, nullable=False)
    line_id:          Mapped[int]      = mapped_column(Integer, ForeignKey("master_lines.id", ondelete="RESTRICT"), nullable=False)
    shift_id:         Mapped[int]      = mapped_column(Integer, ForeignKey("master_shifts.id", ondelete="RESTRICT"), nullable=False)
    feed_code_id:     Mapped[int|None] = mapped_column(Integer, ForeignKey("master_feed_codes.id", ondelete="SET NULL"), nullable=True)
    loss_l1_id:       Mapped[int|None] = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_1.machine_losses_lvl_1_id", ondelete="RESTRICT"), nullable=True)
    loss_l2_id:       Mapped[int|None] = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_2.machine_losses_lvl_2_id", ondelete="RESTRICT"), nullable=True)
    loss_l3_id:       Mapped[int|None] = mapped_column(Integer, ForeignKey("master_machine_losses_lvl_3.machine_losses_lvl_3_id", ondelete="RESTRICT"), nullable=True)
    time_from:        Mapped[str|None] = mapped_column(String(8))
    time_to:          Mapped[str|None] = mapped_column(String(8))
    duration_minutes: Mapped[float]    = mapped_column(Float, nullable=False)
    remarks:          Mapped[str|None] = mapped_column(String(500))
    is_active:        Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id:    Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:       Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:    Mapped[int|None] = mapped_column(Integer, nullable=True)

    line:      Mapped["MasterLine"]              = relationship("MasterLine")
    shift:     Mapped["MasterShift"]             = relationship("MasterShift")
    feed_code: Mapped["MasterFeedCode|None"]     = relationship("MasterFeedCode")
    loss_l1:   Mapped["MachineLossLvl1|None"]    = relationship("MachineLossLvl1", foreign_keys=[loss_l1_id])
    loss_l2:   Mapped["MachineLossLvl2|None"]    = relationship("MachineLossLvl2", foreign_keys=[loss_l2_id])
    loss_l3:   Mapped["MachineLossLvl3|None"]    = relationship("MachineLossLvl3", foreign_keys=[loss_l3_id])


# ─── Equipment Tree ───────────────────────────────────────────────────────────

class EquipmentTree(PlantBase):
    """
    master_equipment_tree — hierarki 5 level:
      sistem → sub_sistem → unit_mesin → bagian_mesin → spare_part

    Setiap baris = satu spare part lengkap dengan konteks hierarkinya.
    Kolom spesifikasi, sku, bu bersifat opsional.
    """
    __tablename__ = "master_equipment_tree"

    id:               Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    sistem:           Mapped[str]      = mapped_column(String(200), nullable=False)
    sub_sistem:       Mapped[str|None] = mapped_column(String(200))
    unit_mesin:       Mapped[str|None] = mapped_column(String(200))
    bagian_mesin:     Mapped[str|None] = mapped_column(String(200))
    spare_part:       Mapped[str|None] = mapped_column(String(200))
    spesifikasi:      Mapped[str|None] = mapped_column(String(500))
    sku:              Mapped[str|None] = mapped_column(String(100))
    bu:               Mapped[str|None] = mapped_column(String(50))
    is_verified:      Mapped[bool]     = mapped_column(Boolean, default=False)
    verified_by_id:   Mapped[int|None] = mapped_column(Integer, nullable=True)
    verified_at:      Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    remarks:          Mapped[str|None] = mapped_column(String(500))
    is_active:        Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by_id:    Mapped[int|None] = mapped_column(Integer, nullable=True)
    updated_at:       Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by_id:    Mapped[int|None] = mapped_column(Integer, nullable=True)